from argon2 import PasswordHasher

_ph = PasswordHasher()


def hash_pw(pw: str) -> str:
    return _ph.hash(pw)


def verify_pw(hash_: str, pw: str) -> bool:
    try:
        _ph.verify(hash_, pw)
        return True
    except Exception:
        return False
