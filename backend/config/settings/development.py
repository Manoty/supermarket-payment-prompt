# backend/config/settings/development.py

from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '.ngrok-free.app']

# Allow React dev server
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',   # Vite default port
    'http://127.0.0.1:5173',
]

CORS_ALLOW_CREDENTIALS = True

# Show full errors in development
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',  # DRF browser UI
]