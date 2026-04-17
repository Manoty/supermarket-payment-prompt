import base64
import logging
import requests
from datetime import datetime
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('apps.payments')

# --- Constants ---
SANDBOX_BASE_URL = 'https://sandbox.safaricom.co.ke'
PRODUCTION_BASE_URL = 'https://api.safaricom.co.ke'
ACCESS_TOKEN_CACHE_KEY = 'mpesa_access_token'
ACCESS_TOKEN_CACHE_TIMEOUT = 3500  # Safaricom tokens last 3600s, cache for slightly less


class MpesaService:
    """
    Low-level Daraja API client.
    Responsible for:
      - Generating access tokens (with caching)
      - Building STK Push requests
      - Nothing else — no DB access, no business logic
    """

    def __init__(self):
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL
        self.environment = settings.MPESA_ENVIRONMENT
        self.base_url = (
            SANDBOX_BASE_URL
            if self.environment == 'sandbox'
            else PRODUCTION_BASE_URL
        )

    # -------------------------------------------------------------------------
    # Access Token
    # -------------------------------------------------------------------------

    def get_access_token(self) -> str:
        """
        Fetch a Daraja API access token.
        Tokens are cached in Redis for ~58 minutes to avoid hitting
        Safaricom's rate limits on the auth endpoint.
        """
        # Check cache first
        cached_token = cache.get(ACCESS_TOKEN_CACHE_KEY)
        if cached_token:
            logger.debug("M-Pesa access token retrieved from cache")
            return cached_token

        logger.info("Fetching new M-Pesa access token from Daraja")

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"

        # Basic auth: base64(consumerKey:consumerSecret)
        credentials = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode()
        ).decode('utf-8')

        try:
            response = requests.get(
                url,
                headers={
                    'Authorization': f'Basic {credentials}',
                    'Content-Type': 'application/json',
                },
                timeout=30
            )
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data['access_token']

            # Cache the token
            cache.set(ACCESS_TOKEN_CACHE_KEY, access_token, ACCESS_TOKEN_CACHE_TIMEOUT)
            logger.info("M-Pesa access token fetched and cached successfully")

            return access_token

        except requests.exceptions.Timeout:
            logger.error("Timeout fetching M-Pesa access token")
            raise MpesaTokenError("Daraja auth endpoint timed out")

        except requests.exceptions.ConnectionError:
            logger.error("Connection error fetching M-Pesa access token")
            raise MpesaTokenError("Could not connect to Daraja API")

        except (requests.exceptions.HTTPError, KeyError) as e:
            logger.error(f"Failed to fetch M-Pesa access token: {e}")
            raise MpesaTokenError(f"Failed to obtain access token: {str(e)}")

    # -------------------------------------------------------------------------
    # Password + Timestamp
    # -------------------------------------------------------------------------

    def _generate_password(self) -> tuple[str, str]:
        """
        Generate the STK push password and timestamp.
        Password = base64(Shortcode + Passkey + Timestamp)
        Timestamp = YYYYMMDDHHmmss in Nairobi time
        """
        import pytz
        nairobi_tz = pytz.timezone('Africa/Nairobi')
        timestamp = datetime.now(nairobi_tz).strftime('%Y%m%d%H%M%S')
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(raw.encode()).decode('utf-8')
        return password, timestamp

    # -------------------------------------------------------------------------
    # STK Push
    # -------------------------------------------------------------------------

    def initiate_stk_push(
        self,
        phone_number: str,
        amount: int,
        account_reference: str,
        transaction_desc: str,
    ) -> dict:
        """
        Send STK Push request to Safaricom.

        Args:
            phone_number: E.164 format (254XXXXXXXXX)
            amount: Integer KES amount (M-Pesa doesn't accept decimals)
            account_reference: Shown on user's phone (e.g. order ID or shop name)
            transaction_desc: Description shown in M-Pesa (max 13 chars recommended)

        Returns:
            dict with MerchantRequestID, CheckoutRequestID, ResponseCode etc.

        Raises:
            MpesaSTKError: if Safaricom returns an error or request fails
        """
        access_token = self.get_access_token()
        password, timestamp = self._generate_password()
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,           # Paying phone number
            "PartyB": self.shortcode,         # Receiving shortcode
            "PhoneNumber": phone_number,      # Phone to send prompt to
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],  # Max 12 chars
            "TransactionDesc": transaction_desc[:13],    # Max 13 chars
        }

        logger.info(
            f"Initiating STK Push | Phone: {phone_number} | "
            f"Amount: KES {amount} | Reference: {account_reference}"
        )

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                },
                timeout=30
            )
            response.raise_for_status()
            response_data = response.json()

            logger.info(
                f"STK Push response | "
                f"ResponseCode: {response_data.get('ResponseCode')} | "
                f"CheckoutRequestID: {response_data.get('CheckoutRequestID')}"
            )

            # ResponseCode '0' means Safaricom accepted the request
            if response_data.get('ResponseCode') != '0':
                error_msg = response_data.get('errorMessage', 'Unknown error from Safaricom')
                logger.error(f"STK Push rejected by Safaricom: {error_msg}")
                raise MpesaSTKError(error_msg, response_data)

            return response_data

        except requests.exceptions.Timeout:
            logger.error(f"STK Push timeout | Phone: {phone_number}")
            raise MpesaSTKError("STK Push request timed out")

        except requests.exceptions.ConnectionError:
            logger.error("STK Push connection error")
            raise MpesaSTKError("Could not connect to Safaricom")

        except requests.exceptions.HTTPError as e:
            logger.error(f"STK Push HTTP error: {e} | Response: {response.text}")
            raise MpesaSTKError(f"HTTP error from Safaricom: {str(e)}")


# -------------------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------------------

class MpesaTokenError(Exception):
    """Raised when we cannot obtain a Daraja access token."""
    pass


class MpesaSTKError(Exception):
    """Raised when STK Push fails."""
    def __init__(self, message: str, response_data: dict = None):
        self.message = message
        self.response_data = response_data or {}
        super().__init__(message)