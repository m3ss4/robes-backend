import os
import httpx
from jose import jwk, jwt

APPLE_ISS = os.getenv("APPLE_ISS", "https://appleid.apple.com")
APPLE_AUDIENCE = os.environ.get("APPLE_AUDIENCE", "")


async def verify_apple_identity_token(token: str) -> dict:
    async with httpx.AsyncClient() as client:
        jwks = (await client.get(f"{APPLE_ISS}/auth/keys")).json()
    headers = jwt.get_unverified_header(token)
    kid = headers["kid"]
    key = next(k for k in jwks["keys"] if k["kid"] == kid)
    claims = jwt.decode(token, jwk.construct(key), algorithms=[key["alg"]], audience=APPLE_AUDIENCE, issuer=APPLE_ISS)
    return claims
