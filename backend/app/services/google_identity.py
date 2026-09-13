"""The Google Identity boundary (030): verifying a Google ID token lives
here and nowhere else. Tests stub `verify`; nothing in the suite touches
the network.

The ID-token flow: Google Identity Services hands the browser a signed
JWT, the browser POSTs it to /auth/google, and this module checks the
signature against Google's published JWKS, the issuer, the audience
(our client id), and the expiry, then returns the three claims the
sign-in needs plus the display name. The token is verified and
discarded; nothing Google issues is stored.

The dependency is PyJWT with its cryptography extra, chosen over
google-auth in the 030 changelog: one package instead of three, a JWKS
client that caches keys and follows key rotation, no HTTP library of
its own (stdlib urllib), and the checks below are explicit rather than
inside a helper.
"""

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.config import settings

# Google publishes its current signing keys here; PyJWKClient caches
# them and refetches on an unknown key id.
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# Google signs ID tokens with either issuer string.
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
GOOGLE_ALGORITHMS = ["RS256"]
JWKS_CACHE_SECONDS = 3600


class GoogleIdentityError(Exception):
    """The token is unusable — bad signature, wrong audience or issuer,
    expired, malformed, no email claim, or the feature is not
    configured. The caller answers one constant refusal for every case."""


@dataclass
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    # Google's `name` claim; empty when the token carries none.
    name: str


_jwks_client: PyJWKClient | None = None


def _client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            GOOGLE_JWKS_URL, cache_keys=True, lifespan=JWKS_CACHE_SECONDS
        )
    return _jwks_client


def verify(credential: str) -> GoogleIdentity:
    """A verified GoogleIdentity, or GoogleIdentityError."""
    if not settings.google_configured:
        raise GoogleIdentityError("GOOGLE_CLIENT_ID is not configured")
    try:
        signing_key = _client().get_signing_key_from_jwt(credential)
        claims = jwt.decode(
            credential,
            signing_key.key,
            algorithms=GOOGLE_ALGORITHMS,
            audience=settings.google_client_id,
            issuer=list(GOOGLE_ISSUERS),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except (jwt.PyJWTError, ValueError) as error:
        raise GoogleIdentityError(str(error)) from error
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise GoogleIdentityError("the token carries no email claim")
    return GoogleIdentity(
        sub=str(claims["sub"]),
        email=email,
        email_verified=claims.get("email_verified") is True,
        name=str(claims.get("name") or ""),
    )
