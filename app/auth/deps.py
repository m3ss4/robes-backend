from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.jwt import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user_id(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    try:
        data = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    if data.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return data["sub"]


def get_user_id_optional(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> Optional[str]:
    if not creds:
        return None
    try:
        data = decode_token(creds.credentials)
        if data.get("typ") != "access":
            return None
        return data["sub"]
    except Exception:
        return None
