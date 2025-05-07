from datetime import datetime, timedelta
from jose import jwt
from fastapi import HTTPException
from config import SECRET, ALGO, ACCESS_TTL

def make_tokens(sub: str):
    now = datetime.utcnow()
    access = jwt.encode({"sub": sub, "exp": now + ACCESS_TTL}, SECRET, algorithm=ALGO)
    refresh = jwt.encode({"sub": sub, "exp": now + timedelta(days=30)}, SECRET, algorithm=ALGO)
    return access, refresh

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        return payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
