# backend/apps/payments/views.py

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle

from .serializers import InitiatePaymentSerializer
from .services.payment_service import (
    PaymentService,
    PaymentValidationError,
    PaymentInitiationError,
    PaymentNotFoundError,
)
from .services.webhook_service import WebhookService

logger = logging.getLogger('apps.payments')


class PaymentRateThrottle(AnonRateThrottle):
    """Stricter rate limit specifically for payment initiation: 5/min per IP."""
    rate = '5/min'


class InitiatePaymentView(APIView):
    """
    POST /api/payments/initiate/
    Validates input, triggers STK Push, returns transaction ID.
    """
    throttle_classes = [PaymentRateThrottle]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {'error': True, 'detail': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        phone_number = serializer.validated_data['phone_number']
        amount = serializer.validated_data['amount']

        try:
            service = PaymentService()
            result = service.initiate_payment(
                phone_number=phone_number,
                amount=amount,
            )
            return Response(result, status=status.HTTP_201_CREATED)

        except PaymentValidationError as e:
            return Response(
                {'error': True, 'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except PaymentInitiationError as e:
            return Response(
                {'error': True, 'detail': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )

        except Exception as e:
            logger.exception(f"Unexpected error in InitiatePaymentView: {e}")
            return Response(
                {'error': True, 'detail': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentStatusView(APIView):
    """
    GET /api/payments/status/<transaction_id>/
    Frontend polls this every 3 seconds to check payment status.
    """

    def get(self, request, transaction_id):
        try:
            service = PaymentService()
            result = service.get_transaction_status(transaction_id)
            return Response(result, status=status.HTTP_200_OK)

        except PaymentNotFoundError as e:
            return Response(
                {'error': True, 'detail': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            logger.exception(f"Unexpected error in PaymentStatusView: {e}")
            return Response(
                {'error': True, 'detail': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MpesaCallbackView(APIView):
    """
    POST /api/payments/callback/
    Receives STK Push result from Safaricom.

    IMPORTANT:
    - Must return HTTP 200 quickly — Safaricom will retry if we don't
    - No authentication required (Safaricom doesn't send auth headers)
    - We validate by matching CheckoutRequestID to our DB records
    """
    authentication_classes = []   # No auth — Safaricom can't authenticate
    permission_classes = []       # Public endpoint

    def post(self, request):
        payload = request.data

        logger.info(f"M-Pesa callback received | IP: {request.META.get('REMOTE_ADDR')}")

        if not payload:
            logger.warning("Empty callback payload received")
            return Response(
                {'ResultCode': 0, 'ResultDesc': 'Accepted'},
                status=status.HTTP_200_OK
            )

        try:
            service = WebhookService()
            service.process_stk_callback(payload)

        except Exception as e:
            # NEVER return non-200 to Safaricom or they will retry endlessly
            # Log the error but always acknowledge receipt
            logger.exception(f"Error processing M-Pesa callback: {e}")

        # Always return this exact format — Safaricom requires it
        return Response(
            {'ResultCode': 0, 'ResultDesc': 'Accepted'},
            status=status.HTTP_200_OK
        )