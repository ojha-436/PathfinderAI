from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User
from app.security import decode_access_token

# Optional scheme for guest support
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_optional_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> Optional[User]:
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload:
        return None
    if payload.get("purpose"):          # reset/special-purpose tokens are not session tokens
        return None

    user_id: str = payload.get("sub")
    if user_id is None:
        return None
        
    user = db.query(User).filter(User.id == user_id).first()
    return user

def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
