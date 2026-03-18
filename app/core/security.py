import logging

import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

# Fetch and cache the public keys from Supabase's JWKS endpoint.
# Supabase uses ES256 (asymmetric) signing — we verify with the public key.
_jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(_jwks_url, cache_keys=True)


def decode_jwt(token: str) -> dict:
    """Decode and verify a Supabase-issued JWT using the project's JWKS public key.

    Returns the full payload dict. Raises 401 on any verification failure.
    """
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )
