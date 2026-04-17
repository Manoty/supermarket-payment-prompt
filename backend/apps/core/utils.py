# backend/apps/core/utils.py

import uuid


def generate_idempotency_key() -> str:
    """Generate a unique idempotency key for payment requests."""
    return str(uuid.uuid4())