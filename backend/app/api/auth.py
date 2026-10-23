import hmac
import hashlib
import time
from fastapi import APIRouter, HTTPException, Depends, Header
from app.config import settings
from app.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

def generate_session_token(password: str) -> str:
    """Generate a simple signed token for session authentication."""
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.APP_PASSWORD.encode("utf-8"),
        f"{password}:{timestamp}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{timestamp}:{signature}"

def verify_token(token: str) -> bool:
    """Verify session token."""
    try:
        parts = token.split(":")
        if len(parts) != 2:
            return False
        timestamp, sig = parts
        expected_sig = hmac.new(
            settings.APP_PASSWORD.encode("utf-8"),
            f"{settings.APP_PASSWORD}:{timestamp}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    """Authenticate teacher using the application password."""
    if payload.password != settings.APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password. Please check your credentials.")

    token = generate_session_token(payload.password)
    return LoginResponse(token=token, authenticated=True)

def require_auth(authorization: str = Header(None)):
    """Optional token enforcement dependency."""
    if not authorization:
        # Permissive for development/demo; can be toggled
        return True
    clean_token = authorization.replace("Bearer ", "").strip()
    if not verify_token(clean_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return True
