import jwt
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt

SECRET_KEY = "simusbet_secret_very_secure_123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 ore

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ─────────────────────────────────────────────────────────────────
#  JWT — tutti i dati nel token, get_current_user non tocca mai DB
# ─────────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise ValueError("no sub")
        return {"username": username, "role": payload.get("role", "user"), "id": payload.get("id")}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def check_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Privilegi insufficienti")
    return user

# ─────────────────────────────────────────────────────────────────
#  bcrypt in thread separato — non blocca l'event loop (~200ms CPU)
# ─────────────────────────────────────────────────────────────────
def _verify_pw_sync(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def _hash_pw_sync(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=10)).decode()

async def verify_password(plain: str, hashed: str) -> bool:
    return await asyncio.get_event_loop().run_in_executor(None, _verify_pw_sync, plain, hashed)

async def get_password_hash(plain: str) -> str:
    return await asyncio.get_event_loop().run_in_executor(None, _hash_pw_sync, plain)

# Alias sincroni per compatibilità
def verify_password_sync(plain: str, hashed: str) -> bool:
    return _verify_pw_sync(plain, hashed)

def get_password_hash_sync(plain: str) -> str:
    return _hash_pw_sync(plain)
