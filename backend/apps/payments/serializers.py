# backend/apps/payments/serializers.py

import re
from rest_framework import serializers
from .models import PaymentTransaction


class InitiatePaymentSerializer(serializers.Serializer):

    phone_number = serializers.CharField(max_length=15)
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=1,
        max_value=150000,
    )

    def validate_phone_number(self, value):
        # Strip all formatting
        value = value.strip().replace(' ', '').replace('-', '').replace('+', '')

        # Allow only digits
        if not value.isdigit():
            raise serializers.ValidationError(
                "Phone number must contain digits only"
            )

        if len(value) < 9:
            raise serializers.ValidationError(
                "Phone number is too short"
            )

        return value

    def validate_amount(self, value):
        # Reject amounts with more than 2 decimal places
        if value != round(value, 2):
            raise serializers.ValidationError(
                "Amount cannot have more than 2 decimal places"
            )
        return value


class PaymentTransactionSerializer(serializers.ModelSerializer):

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