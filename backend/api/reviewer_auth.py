# backend/api/reviewer_auth.py

import base64
import hashlib
import hmac
import os
import time
from typing import Dict

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/reviewer-auth", tags=["reviewer-auth"])

TOKEN_TTL_SECONDS = 12 * 60 * 60


class ReviewerLoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


def _reviewer_password() -> str:
    password = os.getenv("REVIEWER_PASSWORD", "")
    if not password:
        raise HTTPException(
            status_code=503,
            detail="REVIEWER_PASSWORD environment variable is not configured.",
        )
    return password


def _signing_key() -> bytes:
    # 별도 secret을 설정하면 그 값을 우선 사용한다.
    # 없으면 REVIEWER_PASSWORD에서 파생한다.
    secret = os.getenv("REVIEWER_TOKEN_SECRET", "").strip()
    if secret:
        return secret.encode("utf-8")

    password = _reviewer_password()
    return hashlib.sha256(
        ("omp-reviewer-token-v1:" + password).encode("utf-8")
    ).digest()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_reviewer_token() -> tuple[str, int]:
    issued_at = int(time.time())
    expires_at = issued_at + TOKEN_TTL_SECONDS
    payload = f"{issued_at}.{expires_at}".encode("utf-8")
    signature = hmac.new(
        _signing_key(),
        payload,
        hashlib.sha256,
    ).digest()

    token = f"{_b64url_encode(payload)}.{_b64url_encode(signature)}"
    return token, expires_at


def verify_reviewer_token_value(token: str) -> Dict[str, int]:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _b64url_decode(payload_b64)
        supplied_signature = _b64url_decode(signature_b64)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid reviewer token.") from exc

    expected_signature = hmac.new(
        _signing_key(),
        payload,
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid reviewer token.")

    try:
        issued_at_text, expires_at_text = payload.decode("utf-8").split(".", 1)
        issued_at = int(issued_at_text)
        expires_at = int(expires_at_text)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid reviewer token.") from exc

    now = int(time.time())
    if expires_at < now:
        raise HTTPException(status_code=401, detail="Reviewer token expired.")

    return {
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def require_reviewer_token(
    authorization: str | None = Header(default=None),
) -> Dict[str, int]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Reviewer authentication required.")

    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Reviewer authentication required.")

    return verify_reviewer_token_value(token)


@router.post("/login")
def reviewer_login(payload: ReviewerLoginRequest):
    expected = _reviewer_password()

    if not hmac.compare_digest(payload.password, expected):
        raise HTTPException(status_code=401, detail="Incorrect reviewer password.")

    token, expires_at = create_reviewer_token()
    return {
        "status": "ok",
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "expires_in_seconds": TOKEN_TTL_SECONDS,
    }


@router.get("/verify")
def reviewer_verify(auth=Header(default=None, alias="Authorization")):
    # Header alias를 명시해 일반적인 Authorization 헤더를 받는다.
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Reviewer authentication required.")

    token = auth[len("Bearer ") :].strip()
    info = verify_reviewer_token_value(token)
    return {"status": "ok", **info}
