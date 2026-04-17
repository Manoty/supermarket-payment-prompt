# backend/apps/payments/services/webhook_service.py

import logging
from apps.payments.repositories.payment_repository import PaymentRepository

logger = logging.getLogger('apps.payments')

# M-Pesa result codes
MPESA_SUCCESS_CODE = '0'
MPESA_CANCELLED_BY_USER = '1032'
MPESA_TIMEOUT_CODE = '1037'


class WebhookService:
    """
    Handles incoming M-Pesa STK Push callbacks.
    Parses the raw payload, finds the transaction, updates its status.
    """

    def __init__(self):
        self.repo = PaymentRepository()

    def process_stk_callback(self, payload: dict) -> dict:
        """
        Parse and process an M-Pesa STK Push callback.

        M-Pesa callback structure:
        {
          "Body": {
            "stkCallback": {
              "MerchantRequestID": "...",
              "CheckoutRequestID": "ws_CO_...",
              "ResultCode": 0,
              "ResultDesc": "The service request is processed successfully.",
              "CallbackMetadata": {          ← only present on SUCCESS
                "Item": [
                  {"Name": "Amount", "Value": 100},
                  {"Name": "MpesaReceiptNumber", "Value": "QKS4Y5NLMN"},
                  {"Name": "TransactionDate", "Value": 20240101120000},
                  {"Name": "PhoneNumber", "Value": 254712345678}
                ]
              }
            }
          }
        }
        """
        logger.info(f"Received M-Pesa callback: {payload}")

        try:
            stk_callback = payload['Body']['stkCallback']
        except (KeyError, TypeError):
            logger.error(f"Malformed M-Pesa callback payload: {payload}")
            return {'success': False, 'error': 'Malformed payload'}

        checkout_request_id = stk_callback.get('CheckoutRequestID')
        result_code = str(stk_callback.get('ResultCode', ''))
        result_desc = stk_callback.get('ResultDesc', '')

        logger.info(
            f"STK Callback | CheckoutRequestID: {checkout_request_id} | "
            f"ResultCode: {result_code} | Desc: {result_desc}"
        )

        # --- Find our transaction ---
        transaction = self.repo.get_by_checkout_request_id(checkout_request_id)

        if not transaction:
            logger.error(
                f"Callback received for unknown CheckoutRequestID: {checkout_request_id}"
            )
            # Still return 200 to Safaricom — they will retry if we return non-200
            return {
                'success': False,
                'error': f'Transaction not found: {checkout_request_id}'
            }

        # --- Guard: already processed ---
        if transaction.is_terminal:
            logger.warning(
                f"Callback received for already-terminal transaction: {transaction.id} "
                f"| Status: {transaction.status}"
            )
            return {
                'success': True,
                'message': 'Already processed',
                'transaction_id': str(transaction.id),
            }

        # --- Process by result code ---
        if result_code == MPESA_SUCCESS_CODE:
            return self._handle_success(transaction, stk_callback, payload)

        elif result_code == MPESA_CANCELLED_BY_USER:
            return self._handle_cancelled(transaction, result_desc, payload)

        elif result_code == MPESA_TIMEOUT_CODE:
            return self._handle_timeout_callback(transaction, result_desc, payload)

        else:
            return self._handle_failure(transaction, result_code, result_desc, payload)

    def _handle_success(self, transaction, stk_callback: dict, raw: dict) -> dict:
        """Extract metadata and mark transaction as SUCCESS."""
        metadata = self._extract_callback_metadata(
            stk_callback.get('CallbackMetadata', {})
        )

        receipt_number = metadata.get('MpesaReceiptNumber', '')
        result_desc = stk_callback.get('ResultDesc', 'Success')

        if not receipt_number:
            logger.error(
                f"Success callback missing MpesaReceiptNumber | "
                f"TxnID: {transaction.id}"
            )

        transaction.mark_success(
            receipt_number=receipt_number,
            response_description=result_desc,
            raw_callback=raw,
        )

        logger.info(
            f"Payment SUCCESS | TxnID: {transaction.id} | "
            f"Phone: {transaction.phone_number} | "
            f"Amount: KES {transaction.amount} | "
            f"Receipt: {receipt_number}"
        )

        return {
            'success': True,
            'transaction_id': str(transaction.id),
            'receipt_number': receipt_number,
        }

    def _handle_cancelled(self, transaction, result_desc: str, raw: dict) -> dict:
        """User dismissed the STK prompt."""
        from apps.payments.models import TransactionStatus

        transaction.status = TransactionStatus.CANCELLED
        transaction.failure_reason = 'Payment cancelled by user'
        transaction.mpesa_response_code = '1032'
        transaction.mpesa_response_description = result_desc
        transaction.callback_raw = raw
        transaction.save(update_fields=[
            'status', 'failure_reason', 'mpesa_response_code',
            'mpesa_response_description', 'callback_raw', 'updated_at'
        ])

        logger.info(
            f"Payment CANCELLED by user | TxnID: {transaction.id} | "
            f"Phone: {transaction.phone_number}"
        )

        return {
            'success': True,
            'transaction_id': str(transaction.id),
            'status': 'CANCELLED',
        }

    def _handle_timeout_callback(self, transaction, result_desc: str, raw: dict) -> dict:
        """Safaricom sent a timeout result code."""
        transaction.mark_failed(
            response_code='1037',
            response_description=result_desc,
            raw_callback=raw,
        )

        logger.info(
            f"Payment TIMEOUT (from callback) | TxnID: {transaction.id}"
        )

        return {
            'success': True,
            'transaction_id': str(transaction.id),
            'status': 'TIMEOUT',
        }

    def _handle_failure(
        self, transaction, result_code: str,
        result_desc: str, raw: dict
    ) -> dict:
        """Any other failure code from Safaricom."""
        transaction.mark_failed(
            response_code=result_code,
            response_description=result_desc,
            raw_callback=raw,
        )

        logger.warning(
            f"Payment FAILED | TxnID: {transaction.id} | "
            f"Code: {result_code} | Desc: {result_desc}"
        )

        return {
            'success': True,
            'transaction_id': str(transaction.id),
            'status': 'FAILED',
        }

    @staticmethod
    def _extract_callback_metadata(metadata: dict) -> dict:
        """
        Flatten M-Pesa's awkward metadata format into a simple dict.

        Input:  {"Item": [{"Name": "Amount", "Value": 100}, ...]}
        Output: {"Amount": 100, "MpesaReceiptNumber": "QKS4Y5NLMN", ...}
        """
        result = {}
        items = metadata.get('Item', [])
        for item in items:
            name = item.get('Name')
            value = item.get('Value')
            if name:
                result[name] = value
        return result