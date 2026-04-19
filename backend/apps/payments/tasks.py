# backend/apps/payments/tasks.py

import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger('apps.payments')


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,   # retry after 10 seconds
    name='payments.initiate_stk_push',
)
def initiate_stk_push_task(self, transaction_id: str, phone_number: str, amount: str):
    """
    Async STK Push task.
    Runs off the request thread so the user gets an immediate response.
    Retries up to 3 times on network failures.
    """
    from apps.payments.services.mpesa_service import MpesaService, MpesaSTKError, MpesaTokenError
    from apps.payments.repositories.payment_repository import PaymentRepository
    from apps.payments.models import TransactionStatus

    repo = PaymentRepository()
    transaction = repo.get_by_id(transaction_id)

    if not transaction:
        logger.error(f"Task: Transaction {transaction_id} not found")
        return

    if transaction.is_terminal:
        logger.warning(f"Task: Transaction {transaction_id} already terminal — skipping")
        return

    logger.info(f"Task: Initiating STK Push for TxnID: {transaction_id}")

    try:
        mpesa = MpesaService()
        stk_response = mpesa.initiate_stk_push(
            phone_number=phone_number,
            amount=int(float(amount)),
            account_reference='CleanShelfMart',
            transaction_desc='Payment',
        )

        # Update transaction with M-Pesa IDs
        repo.update_mpesa_ids(
            transaction=transaction,
            merchant_request_id=stk_response['MerchantRequestID'],
            checkout_request_id=stk_response['CheckoutRequestID'],
        )

        logger.info(
            f"Task: STK Push sent | TxnID: {transaction_id} | "
            f"CheckoutRequestID: {stk_response['CheckoutRequestID']}"
        )

        # Schedule timeout check — runs after 2 minutes
        check_payment_timeout.apply_async(
            args=[transaction_id],
            countdown=120,   # 2 minutes
        )

    except (MpesaSTKError, MpesaTokenError) as e:
        logger.warning(f"Task: STK Push failed | TxnID: {transaction_id} | Error: {e}")
        try:
            # Retry the task
            transaction.retry_count += 1
            transaction.save(update_fields=['retry_count', 'updated_at'])
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            # All retries exhausted — mark as failed
            logger.error(f"Task: Max retries exceeded | TxnID: {transaction_id}")
            transaction.mark_failed(
                response_code='MAX_RETRIES',
                response_description='Payment initiation failed after maximum retries',
                raw_callback={},
            )

    except Exception as e:
        logger.exception(f"Task: Unexpected error | TxnID: {transaction_id} | {e}")
        transaction.mark_failed(
            response_code='TASK_ERROR',
            response_description=str(e),
            raw_callback={},
        )


@shared_task(name='payments.check_payment_timeout')
def check_payment_timeout(transaction_id: str):
    """
    Called 2 minutes after STK Push is sent.
    If the transaction is still PENDING, it means we never got a callback
    — mark it as TIMEOUT.
    """
    from apps.payments.repositories.payment_repository import PaymentRepository

    repo = PaymentRepository()
    transaction = repo.get_by_id(transaction_id)

    if not transaction:
        logger.warning(f"Timeout check: Transaction {transaction_id} not found")
        return

    if transaction.is_terminal:
        logger.info(
            f"Timeout check: Transaction {transaction_id} already resolved "
            f"with status {transaction.status} — no action needed"
        )
        return

    # Still PENDING after 2 minutes — timeout
    logger.warning(
        f"Timeout check: Transaction {transaction_id} still PENDING after "
        f"2 minutes — marking as TIMEOUT"
    )
    transaction.mark_timeout()