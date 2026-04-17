# backend/apps/payments/serializers.py

from rest_framework import serializers
from .models import PaymentTransaction


class InitiatePaymentSerializer(serializers.Serializer):
    """Validates incoming payment request from the frontend."""

    phone_number = serializers.CharField(
        max_length=15,
        help_text="Phone number: 07XXXXXXXX or 254XXXXXXXXX"
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=1,
        max_value=150000,
        help_text="Amount in KES (1 - 150,000)"
    )

    def validate_phone_number(self, value):
        """Strip whitespace and basic sanity check."""
        value = value.strip().replace(' ', '').replace('-', '')
        if len(value) < 9:
            raise serializers.ValidationError("Phone number is too short")
        return value


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Read-only serializer for returning transaction data."""

    class Meta:
        model = PaymentTransaction
        fields = [
            'id',
            'phone_number',
            'amount',
            'status',
            'mpesa_receipt_number',
            'failure_reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields