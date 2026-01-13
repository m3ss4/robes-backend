import os
import time
import jwt
from typing import Any, Dict

ALG = os.getenv("JWT_ALG", "HS256")
SECRET = os.environ.get("JWT_SECRET", "change_me")
ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "3600"))
REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_SECONDS", "2592000"))


def mint_access(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + ACCESS_TTL, "typ": "access"}, SECRET, algorithm=ALG)


def mint_refresh(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + REFRESH_TTL, "typ": "refresh"}, SECRET, algorithm=ALG)


def decode_token(tok: str) -> Dict[str, Any]:
    return jwt.decode(tok, SECRET, algorithms=[ALG])
