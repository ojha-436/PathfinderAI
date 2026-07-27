from __future__ import annotations

import json
import secrets
import smtplib
import sys
import urllib.parse
import urllib.request
from datetime import timedelta
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db, get_current_user
from app.models import User
from app.schemas import (AuthConfig, ForgotRequest, GoogleLogin, PersonaUpdate,
                         ResetRequest, Token, UserCreate, UserLogin, UserResponse)
from app.security import create_access_token, decode_access_token, hash_password, verify_password


router = APIRouter()

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    
    hashed_password, salt = hash_password(user_in.password)
    
    new_user = User(
        email=user_in.email,
        password_hash=hashed_password,
        password_salt=salt,
        iterations=200000
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = create_access_token(data={"sub": new_user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(user_in.password, user.password_hash, user.password_salt, user.iterations):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/extension-token", response_model=Token)
def extension_token(current_user: User = Depends(get_current_user)):
    """Mint a scoped, longer-lived token so the browser extension can bootstrap its
    session from an already-authenticated web session — no separate email/password
    login in the extension. The web app calls this while the user is signed in and
    hands the token to the extension over a trusted page→content-script handshake."""
    token = create_access_token({"sub": current_user.id, "scope": "extension"}, timedelta(days=30))
    return {"access_token": token, "token_type": "bearer"}


@router.patch("/me", response_model=UserResponse)
def update_me(body: PersonaUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if body.persona not in {"student", "professional", "auto"}:
        raise HTTPException(status_code=400, detail="persona must be student|professional|auto")
    current_user.persona = body.persona
    db.commit()
    db.refresh(current_user)
    return current_user

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.delete(current_user)
    db.commit()
    return None


# ---------------------------------------------------------------- Google Sign-In
@router.get("/config", response_model=AuthConfig)
def auth_config():
    """Public config so the frontend can render the Google button only when enabled."""
    return AuthConfig(google_enabled=bool(settings.GOOGLE_CLIENT_ID), google_client_id=settings.GOOGLE_CLIENT_ID)


def _verify_google_credential(credential: str) -> dict:
    """Verify a Google ID token via Google's tokeninfo endpoint; return its claims.
    Raises on any problem (bad signature/audience/unverified email)."""
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": credential})
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise ValueError("audience mismatch")
    if str(data.get("email_verified")).lower() != "true":
        raise ValueError("email not verified")
    if not data.get("email"):
        raise ValueError("no email in token")
    return data


@router.post("/google", response_model=Token)
def google_login(body: GoogleLogin, db: Session = Depends(get_db)):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        info = _verify_google_credential(body.credential)
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify your Google sign-in.")
    email = info["email"].lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        # OAuth account: unusable random password (satisfies NOT NULL); user signs in via Google.
        ph, salt = hash_password(secrets.token_urlsafe(24))
        user = User(email=email, password_hash=ph, password_salt=salt, iterations=200000)
        db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_access_token(data={"sub": user.id}), "token_type": "bearer"}


# ---------------------------------------------------------------- Password reset
def _send_reset_email(to_email: str, link: str) -> None:
    if settings.SMTP_HOST and settings.SMTP_USER:
        try:  # pragma: no cover - depends on external SMTP
            msg = EmailMessage()
            msg["Subject"] = "Reset your PathFinder password"
            msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
            msg["To"] = to_email
            msg.set_content(
                "Reset your PathFinder password using this link (valid for 30 minutes):\n\n"
                f"{link}\n\nIf you didn't request this, you can safely ignore this email."
            )
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
                s.starttls()
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
            return
        except Exception as exc:
            print(f"[PathFinder] reset email send failed: {exc}", file=sys.stderr)
    # No SMTP (or send failed) — log the link so it can be retrieved from server logs.
    print(f"[PathFinder] Password-reset link for {to_email}: {link}", file=sys.stderr)


@router.post("/forgot")
def forgot_password(body: ForgotRequest, request: Request, db: Session = Depends(get_db)):
    email = str(body.email).lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user:
        token = create_access_token({"sub": user.id, "purpose": "reset"}, timedelta(minutes=30))
        base = (settings.APP_BASE_URL or str(request.base_url)).rstrip("/")
        _send_reset_email(user.email, f"{base}/#/reset?token={token}")
    # Always generic — never reveal whether an account exists (no user enumeration).
    return {"detail": "If an account exists for that email, a password reset link has been sent."}


@router.post("/reset")
def reset_password(body: ResetRequest, db: Session = Depends(get_db)):
    payload = decode_access_token(body.token)
    if not payload or payload.get("purpose") != "reset":
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid.")
    ph, salt = hash_password(body.password)
    user.password_hash, user.password_salt, user.iterations = ph, salt, 200000
    db.commit()
    return {"detail": "Your password has been updated — you can now log in."}
