import os

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv


load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

OAUTH_SESSION_SECRET = (
    os.getenv("OAUTH_SESSION_SECRET")
    or os.getenv("AUTH_SECRET_KEY")
)

if not OAUTH_SESSION_SECRET:
    raise RuntimeError(
        "Missing OAUTH_SESSION_SECRET or AUTH_SECRET_KEY",
    )

oauth = OAuth()

if GOOGLE_OAUTH_ENABLED:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url=(
            "https://accounts.google.com/"
            ".well-known/openid-configuration"
        ),
        client_kwargs={
            "scope": "openid email profile",
        },
    )
