import logging
from typing import Optional
from apps.payments.models import PaymentTransaction, TransactionStatus

logger = logging.getLogger('apps.payments')


class PaymentRepository:
    """
    All database operations for PaymentTransaction.
    Views and services never query the DB directly — they go through here.
    This makes testing easy (mock the repository, not the ORM).
    """

    @staticmethod
    def create_transaction(
        phone_number: str,
        amount,
        user=None,
    ) -> PaymentTransaction:
        """Create a new PENDING transaction before sending STK push."""
        transaction = PaymentTransaction.objects.create(
            phone_number=phone_number,
            amount=amount,
            user=user,
            status=TransactionStatus.PENDING,
        )
        logger.info(
            f"Transaction created | ID: {transaction.id} | "
            f"Phone: {phone_number} | Amount: KES {amount}"
        )
        return transaction

    @staticmethod
    def update_mpesa_ids(
        transaction: PaymentTransaction,
        merchant_request_id: str,
        checkout_request_id: str,
    ) -> PaymentTransaction:
        """
        After STK push succeeds, store the M-Pesa identifiers.
        We need checkout_request_id to match the incoming callback.
        """
        transaction.mpesa_merchant_request_id = merchant_request_id
        transaction.mpesa_checkout_request_id = checkout_request_id
        transaction.save(update_fields=[
            'mpesa_merchant_request_id',
            'mpesa_checkout_request_id',
            'updated_at',
        ])
        return transaction

    @staticmethod
    def get_by_id(transaction_id: str) -> Optional[PaymentTransaction]:
        """Fetch transaction by UUID."""
        try:
            return PaymentTransaction.objects.get(id=transaction_id)
        except PaymentTransaction.DoesNotExist:
            return None

    @staticmethod
    def get_by_checkout_request_id(checkout_request_id: str) -> Optional[PaymentTransaction]:
        """
        Fetch transaction by M-Pesa CheckoutRequestID.
        This is the primary lookup used in the webhook callback.
        The field is indexed so this is fast.
        """
        try:
            return PaymentTransaction.objects.get(
                mpesa_checkout_request_id=checkout_request_id
            )
        except PaymentTransaction.DoesNotExist:
            logger.warning(
                f"No transaction found for CheckoutRequestID: {checkout_request_id}"
            )
            return None

    @staticmethod
    def get_pending_transactions_for_phone(phone_number: str):
        """Check for existing PENDING transactions to prevent duplicate pushes."""
        return PaymentTransaction.objects.filter(
            phone_number=phone_number,
            status=TransactionStatus.PENDING,
        )