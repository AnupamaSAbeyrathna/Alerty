import hashlib
import secrets
from typing import Tuple

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey

def generate_api_key(prefix:str = "alerty_") -> Tuple[str, str, str]:
    """
    Generates a secure api key

    Returns (raw_key, key_hash, key_prefix)
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{random_part}"

    #store first 8 chars, so users can identify the key in a UI (e.g. "alerty_a")
    key_prefix = raw_key[:8]

    #one way SHA-256 hash for database storage
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    return raw_key, key_hash, key_prefix

def verify_api_key(
    authorization: str = Header(..., description="API key in format : 'Bearer <key>'"),
    db: Session = Depends(get_db),
    ) -> ApiKey:
    
    """
    FastAPI dependency that extracts and validates the API key.
    Returns the ApiKey ORM instance if valid; raises 401 otherwise.
    """
    #1. validate Header scheme
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Invalid authorization header format. Expected 'Bearer <key>'.", 
        )

    raw_key = authorization.removeprefix("Bearer").strip()
    if not raw_key:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail  = "API key cannot be empty.",
        )

    #2. Hash the incoming raw key
    incoming_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    #3. look up active key in DB
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == incoming_hash, ApiKey.is_active.is_(True))
        .first()
    )

    if not api_key:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Invalid or revoked API key",
        )

    return api_key