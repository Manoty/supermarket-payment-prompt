# backend/apps/payments/services/payment_service.py

import logging
from decimal import Decimal, InvalidOperation
from apps.payments.repositories.payment_repository import PaymentRepository
from apps.users.models import User

logger = logging.getLogger('apps.payments')

MPESA_MIN_AMOUNT = Decimal('1.00')
MPESA_MAX_AMOUNT = Decimal('150000.00')


class PaymentService:

    def __init__(self):
        self.repo = PaymentRepository()

    def initiate_payment(self, phone_number: str, amount: str) -> dict:
        """
        1. Validate inputs
        2. Create transaction record immediately
        3. Dispatch STK Push to Celery (async)
        4. Return transaction ID to frontend right away
        Frontend then polls /status/<id>/ for updates.
        """

        # --- Validate amount ---
        try:
            amount_decimal = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise PaymentValidationError("Invalid amount format")

        if amount_decimal < MPESA_MIN_AMOUNT:
            raise PaymentValidationError(f"Minimum amount is KES {MPESA_MIN_AMOUNT}")

        if amount_decimal > MPESA_MAX_AMOUNT:
            raise PaymentValidationError(f"Maximum amount is KES {MPESA_MAX_AMOUNT}")

        # --- Normalize + validate phone ---
        phone_number = self._normalize_phone(phone_number)
        self._validate_kenyan_phone(phone_number)

        # --- Block duplicate pending payments ---
        pending = self.repo.get_pending_transactions_for_phone(phone_number)
        if pending.exists():
            logger.warning(f"Duplicate payment blocked | Phone: {phone_number}")
            raise PaymentValidationError(
                "You have a pending payment. Please wait for it to complete."
            )

        # --- Get or create user ---
        user, created = User.objects.get_or_create(phone_number=phone_number)
        if created:
            logger.info(f"New user created | Phone: {phone_number}")

        # --- Create transaction FIRST (before calling Safaricom) ---
        transaction = self.repo.create_transaction(
            phone_number=phone_number,
            amount=amount_decimal,
            user=user,
        )

        # --- Dispatch to Celery ---
        # Import here to avoid circular imports
        from apps.payments.tasks import initiate_stk_push_task

        initiate_stk_push_task.delay(
            transaction_id=str(transaction.id),
            phone_number=phone_number,
            amount=str(amount_decimal),
        )

        logger.info(
            f"Payment queued | TxnID: {transaction.id} | "
            f"Phone: {phone_number} | Amount: KES {amount_decimal}"
        )

        # Return immediately — frontend polls for status
        return {
            'transaction_id': str(transaction.id),
            'phone_number': phone_number,
            'amount': str(amount_decimal),
            'status': transaction.status,
            'message': 'Payment initiated. Please check your phone for the M-Pesa prompt.',
        }

    def get_transaction_status(self, transaction_id: str) -> dict:
        transaction = self.repo.get_by_id(transaction_id)
        if not transaction:
            raise PaymentNotFoundError(f"Transaction {transaction_id} not found")

        return {
            'transaction_id': str(transaction.id),
            'status': transaction.status,
            'phone_number': transaction.phone_number,
            'amount': str(transaction.amount),
            'mpesa_receipt_number': transaction.mpesa_receipt_number,
            'failure_reason': transaction.failure_reason,
            'created_at': transaction.created_at.isoformat(),
            'updated_at': transaction.updated_at.isoformat(),
        }

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        phone = phone.strip().replace(' ', '').replace('-', '').replace('+', '')
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        if not phone.startswith('254'):
            phone = '254' + phone
        return phone

    @staticmethod
    def _validate_kenyan_phone(phone: str):
        if len(phone) != 12:
            raise PaymentValidationError(
                "Invalid phone number. Use format: 07XXXXXXXX or 254XXXXXXXXX"
            )
        if not phone.startswith(('2547', '2541')):
            raise PaymentValidationError(
                "Invalid Kenyan phone number. Must start with 07, 01, 2547, or 2541"
            )


class PaymentValidationError(Exception):
    pass

class PaymentInitiationError(Exception):
    pass

class PaymentNotFoundError(Exception):
    pass