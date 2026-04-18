# backend/apps/payments/models.py

import uuid
from django.db import models
from django.conf import settings


def generate_idempotency_key():
    return uuid.uuid4()


class TransactionStatus(models.TextChoices):
    """
    Explicit state machine for payment lifecycle.
    Using TextChoices so values are human-readable in the DB
    and in admin — never store magic integers.
    """
    PENDING   = 'PENDING',   'Pending'
    SUCCESS   = 'SUCCESS',   'Success'
    FAILED    = 'FAILED',    'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    TIMEOUT   = 'TIMEOUT',   'Timeout'


class PaymentTransaction(models.Model):
    """
    Central record for every payment attempt.

    Design principles:
    - Immutable history : we never DELETE transactions
    - Idempotent        : idempotency_key prevents double charges
    - Auditable         : callback_raw stores full M-Pesa response
    - Decoupled         : phone_number stored directly (not just via FK)
    """

    # --- Identity ---
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    idempotency_key = models.UUIDField(
        default=generate_idempotency_key,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Unique key to prevent duplicate payment processing"
    )

    # --- Relationships ---
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        help_text="Optional link to user account"
    )

    # --- Payment Details ---
    phone_number = models.CharField(
        max_length=15,
        db_index=True,
        help_text="Phone number in E.164 format (254XXXXXXXXX)"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Payment amount in KES"
    )

    # --- Status ---
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True,
    )
    failure_reason = models.TextField(
        blank=True,
        default='',
        help_text="Human-readable reason for failure, if applicable"
    )

    # --- M-Pesa Identifiers ---
    mpesa_merchant_request_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Merchant request ID from STK push response"
    )
    mpesa_checkout_request_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text="Checkout request ID — used to match the M-Pesa callback"
    )
    mpesa_receipt_number = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="M-Pesa receipt number (e.g. QKS4Y5NLMN) — proof of payment"
    )

    # --- Callback Data ---
    mpesa_response_code = models.CharField(
        max_length=10,
        blank=True,
        default='',
        help_text="Result code from M-Pesa callback (0 = success)"
    )
    mpesa_response_description = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Human-readable result description from M-Pesa"
    )
    callback_raw = models.JSONField(
        null=True,
        blank=True,
        help_text="Full raw callback payload from M-Pesa — for auditing"
    )

    # --- Retry Tracking ---
    retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of times we have retried this transaction"
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_transactions'
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['status', 'created_at'],
                name='idx_transaction_status_created'
            ),
            models.Index(
                fields=['phone_number', 'created_at'],
                name='idx_transaction_phone_created'
            ),
        ]

    def __str__(self):
        return f"TXN-{self.id} | {self.phone_number} | KES {self.amount} | {self.status}"

    # -------------------------------------------------------------------------
    # State Transition Methods
    # -------------------------------------------------------------------------

    def mark_success(self, receipt_number: str, response_description: str, raw_callback: dict):
        """Transition to SUCCESS. Only valid from PENDING."""
        if self.status != TransactionStatus.PENDING:
            raise ValueError(f"Cannot mark SUCCESS from status: {self.status}")

        self.status = TransactionStatus.SUCCESS
        self.mpesa_receipt_number = receipt_number
        self.mpesa_response_code = '0'
        self.mpesa_response_description = response_description
        self.callback_raw = raw_callback
        self.save(update_fields=[
            'status', 'mpesa_receipt_number', 'mpesa_response_code',
            'mpesa_response_description', 'callback_raw', 'updated_at',
        ])

    def mark_failed(self, response_code: str, response_description: str, raw_callback: dict):
        """Transition to FAILED. Only valid from PENDING."""
        if self.status != TransactionStatus.PENDING:
            raise ValueError(f"Cannot mark FAILED from status: {self.status}")

        self.status = TransactionStatus.FAILED
        self.mpesa_response_code = response_code
        self.mpesa_response_description = response_description
        self.failure_reason = response_description
        self.callback_raw = raw_callback
        self.save(update_fields=[
            'status', 'mpesa_response_code', 'mpesa_response_description',
            'failure_reason', 'callback_raw', 'updated_at',
        ])

    def mark_timeout(self):
        """Transition to TIMEOUT. Called by Celery if no callback arrives in time."""
        if self.status != TransactionStatus.PENDING:
            return  # Already resolved — silently ignore

        self.status = TransactionStatus.TIMEOUT
        self.failure_reason = 'No callback received within the allowed time window'
        self.save(update_fields=['status', 'failure_reason', 'updated_at'])

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        """True if the transaction is in a final, unchangeable state."""
        return self.status in {
            TransactionStatus.SUCCESS,
            TransactionStatus.FAILED,
            TransactionStatus.CANCELLED,
            TransactionStatus.TIMEOUT,
        }

    @property
    def amount_in_cents(self) -> int:
        """M-Pesa expects integer amounts. Returns amount as int."""
        return int(self.amount)