# backend/apps/payments/urls.py

from django.urls import path
from .views import InitiatePaymentView, PaymentStatusView, MpesaCallbackView

urlpatterns = [
    # Frontend calls this to start a payment
    path('initiate/', InitiatePaymentView.as_view(), name='payment-initiate'),

    # Frontend polls this to check payment status
    path('status/<uuid:transaction_id>/', PaymentStatusView.as_view(), name='payment-status'),

    # Safaricom posts STK push results here
    path('callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
]