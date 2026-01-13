import os
from google.oauth2 import id_token
from google.auth.transport import requests as grequests

GOOGLE_AUDIENCE = os.environ.get("GOOGLE_AUDIENCE", "")


def verify_google_id_token(token: str) -> dict:
    if not GOOGLE_AUDIENCE:
        raise ValueError("GOOGLE_AUDIENCE_not_configured")
    info = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_AUDIENCE or None)
    return info
