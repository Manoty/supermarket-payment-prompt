# backend/apps/core/exceptions.py

import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler to return a consistent
    JSON shape: { "error": "...", "detail": "..." }
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            'error': True,
            'status_code': response.status_code,
            'detail': response.data,
        }
        response.data = error_data
        logger.warning(
            f"API Exception: {exc.__class__.__name__} | "
            f"View: {context.get('view')} | Detail: {exc}"
        )

    return response