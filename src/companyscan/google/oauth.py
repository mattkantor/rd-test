"""Google OAuth for the customer: consent URL, code exchange, refresh, and Fernet encryption of stored tokens.
Knows nothing about listings. Never log tokens or the client secret."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/business.manage"


def setting(name):
    value = os.environ.get(f"GOOGLE_{name}", "")
    if not value:
        raise ValueError(f"Google is not configured: set GOOGLE_{name}")
    return value


def consent_url(state):
    # access_type=offline + prompt=consent so Google always returns a refresh token.
    return AUTH_URL + "?" + urlencode({
        "client_id": setting("OAUTH_CLIENT_ID"), "redirect_uri": setting("OAUTH_REDIRECT_URI"), "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state})


def post(url, data):
    """Form POST returning the JSON object; the one network call here, so tests replace it."""
    with urlopen(Request(url, data=urlencode(data).encode(), method="POST"), timeout=30) as r:
        return json.load(r)


def exchange(code):
    """Tokens for an authorization code: {access_token, refresh_token, expires_in}."""
    return post(TOKEN_URL, {"code": code, "client_id": setting("OAUTH_CLIENT_ID"), "client_secret": setting("OAUTH_CLIENT_SECRET"),
                            "redirect_uri": setting("OAUTH_REDIRECT_URI"), "grant_type": "authorization_code"})


def refresh(refresh_token):
    return post(TOKEN_URL, {"refresh_token": refresh_token, "client_id": setting("OAUTH_CLIENT_ID"),
                            "client_secret": setting("OAUTH_CLIENT_SECRET"), "grant_type": "refresh_token"})


def fernet():
    from cryptography.fernet import Fernet  # Lazy: only the web extra needs it.
    return Fernet(setting("TOKEN_KEY").encode())


def encrypt(text):
    return fernet().encrypt(text.encode()).decode()


def decrypt(text):
    return fernet().decrypt(text.encode()).decode()
