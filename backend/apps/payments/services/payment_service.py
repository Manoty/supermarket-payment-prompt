# backend/apps/payments/services/payment_service.py

import logging
from decimal import Decimal, InvalidOperation
from apps.payments.repositories.payment_repository import PaymentRepository
from apps.payments.services.mpesa_service import MpesaService, MpesaSTKError, MpesaTokenError
from apps.users.models import User

logger = logging.getLogger('apps.payments')

# M-Pesa limits
MPESA_MIN_AMOUNT = Decimal('1.00')
MPESA_MAX_AMOUNT = Decimal('150000.00')


class PaymentService:
    """
    Orchestrates payment flow.
    Calls repository for DB ops, calls MpesaService for API ops.
    This is the only layer that knows about both.
    """

    def __init__(self):
        self.mpesa = MpesaService()
        self.repo = PaymentRepository()

    def initiate_payment(self, phone_number: str, amount: str) -> dict:
        """
        Full payment initiation flow:
        1. Validate inputs
        2. Normalize phone number
        3. Create transaction record
        4. Send STK push
        5. Update transaction with M-Pesa IDs
        6. Return transaction data to caller

        We create the DB record BEFORE calling Safaricom.
        If Safaricom call fails, we still have an audit record.
        """

        # --- 1. Validate amount ---
        try:
            amount_decimal = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise PaymentValidationError("Invalid amount format")

        if amount_decimal < MPESA_MIN_AMOUNT:
            raise PaymentValidationError(
                f"Amount must be at least KES {MPESA_MIN_AMOUNT}"
            )

        if amount_decimal > MPESA_MAX_AMOUNT:
            raise PaymentValidationError(
                f"Amount cannot exceed KES {MPESA_MAX_AMOUNT}"
            )

        # --- 2. Normalize phone ---
        phone_number = self._normalize_phone(phone_number)
        self._validate_kenyan_phone(phone_number)

        # --- 3. Check for duplicate pending transaction ---
        pending = self.repo.get_pending_transactions_for_phone(phone_number)
        if pending.exists():
            logger.warning(
                f"Duplicate payment attempt blocked | Phone: {phone_number}"
            )
            raise PaymentValidationError(
                "You have a pending payment. Please complete or wait for it to expire."
            )

        # --- 4. Get or create user ---
        user, created = User.objects.get_or_create(phone_number=phone_number)
        if created:
            logger.info(f"New user created for phone: {phone_number}")

        # --- 5. Create transaction BEFORE calling Safaricom ---
        transaction = self.repo.create_transaction(
            phone_number=phone_number,
            amount=amount_decimal,
            user=user,
        )

        # --- 6. Send STK Push ---
        try:
            stk_response = self.mpesa.initiate_stk_push(
                phone_number=phone_number,
                amount=int(amount_decimal),         # M-Pesa expects integer
                account_reference='CleanShelfMart', # Your shop name
                transaction_desc='Payment',
            )

            # --- 7. Update transaction with M-Pesa identifiers ---
            transaction = self.repo.update_mpesa_ids(
                transaction=transaction,
                merchant_request_id=stk_response['MerchantRequestID'],
                checkout_request_id=stk_response['CheckoutRequestID'],
            )

            logger.info(
                f"STK Push initiated successfully | "
                f"TxnID: {transaction.id} | "
                f"CheckoutRequestID: {transaction.mpesa_checkout_request_id}"
            )

            return {
                'transaction_id': str(transaction.id),
                'checkout_request_id': transaction.mpesa_checkout_request_id,
                'phone_number': phone_number,
                'amount': str(amount_decimal),
                'status': transaction.status,
                'message': 'STK Push sent. Please enter your M-Pesa PIN.',
            }

        except (MpesaSTKError, MpesaTokenError) as e:
            # STK push failed — mark transaction as FAILED with reason
            transaction.mark_failed(
                response_code='STK_ERROR',
                response_description=str(e),
                raw_callback={},
            )
            logger.error(
                f"STK Push failed | TxnID: {transaction.id} | Error: {e}"
            )
            raise PaymentInitiationError(str(e))

    def get_transaction_status(self, transaction_id: str) -> dict:
        """
        Poll endpoint — frontend calls this every few seconds
        to check if payment completed.
        """
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

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize to E.164 format (254XXXXXXXXX)."""
        phone = phone.strip().replace(' ', '').replace('-', '').replace('+', '')
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        if not phone.startswith('254'):
            phone = '254' + phone
        return phone

    @staticmethod
    def _validate_kenyan_phone(phone: str):
        """
        Validate the phone is a real Kenyan number.
        Must be 254 + 9 digits = 12 chars total.
        Safaricom prefixes: 254 7XX or 254 1XX
        """
        if len(phone) != 12:
            raise PaymentValidationError(
                "Invalid phone number length. Use format: 07XXXXXXXX or 254XXXXXXXXX"
            )
        if not phone.startswith(('2547', '2541')):
            raise PaymentValidationError(
                "Invalid Kenyan phone number. Must start with 07, 01, or 2547, 2541"
            )


# -------------------------------------------------------------------------
# Service Exceptions
# -------------------------------------------------------------------------

class PaymentValidationError(Exception):
    """Input validation failed before we even call Safaricom."""
    pass


class PaymentInitiationError(Exception):
    """STK Push failed at the Safaricom API level."""
    pass


class PaymentNotFoundError(Exception):
    """Transaction ID not found in database."""
    pass