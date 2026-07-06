import hashlib
import hmac
import secrets
import json
import base64
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from app.config import settings

def hash_password(password: str, salt: Optional[str] = None, iterations: int = 200000) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations
    )
    return key.hex(), salt

def verify_password(plain_password: str, hashed_password: str, salt: str, iterations: int = 200000) -> bool:
    new_hash, _ = hash_password(plain_password, salt, iterations)
    return hmac.compare_digest(new_hash, hashed_password)

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def base64url_decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())})
    
    header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}
    
    b64_header = base64url_encode(json.dumps(header).encode('utf-8'))
    b64_payload = base64url_encode(json.dumps(to_encode).encode('utf-8'))
    
    signature_input = f"{b64_header}.{b64_payload}"
    signature = hmac.new(
        settings.JWT_SECRET.encode('utf-8'),
        signature_input.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    b64_signature = base64url_encode(signature)
    return f"{signature_input}.{b64_signature}"

def decode_access_token(token: str) -> Optional[dict]:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        signature_input = f"{parts[0]}.{parts[1]}"
        expected_signature = hmac.new(
            settings.JWT_SECRET.encode('utf-8'),
            signature_input.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        if not hmac.compare_digest(base64url_encode(expected_signature), parts[2]):
            return None
            
        payload = json.loads(base64url_decode(parts[1]).decode('utf-8'))
        
        if "exp" in payload:
            if datetime.now(timezone.utc).timestamp() > payload["exp"]:
                return None
                
        return payload
    except Exception:
        return None
