# backend/apps/payments/views.py — full final version

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
    """5 payment attempts per minute per IP."""
    rate = '5/min'


class InitiatePaymentView(APIView):
    throttle_classes = [PaymentRateThrottle]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {'error': True, 'detail': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = PaymentService()
            result = service.initiate_payment(
                phone_number=serializer.validated_data['phone_number'],
                amount=serializer.validated_data['amount'],
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
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        logger.info(f"M-Pesa callback received | IP: {request.META.get('REMOTE_ADDR')}")

        if not request.data:
            return Response(
                {'ResultCode': 0, 'ResultDesc': 'Accepted'},
                status=status.HTTP_200_OK
            )

        try:
            service = WebhookService()
            service.process_stk_callback(request.data)
        except Exception as e:
            logger.exception(f"Error processing M-Pesa callback: {e}")

        # Always return 200 to Safaricom
        return Response(
            {'ResultCode': 0, 'ResultDesc': 'Accepted'},
            status=status.HTTP_200_OK
        )