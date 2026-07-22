from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.config import settings


pwd_context=CryptContext(schemes=["bcrypt"],deprecated="auto")

ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM="HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


'''
bcrypt hashes passwords with a random salt baked in — even two users with password "123456" get different hashes in the DB. We never store or compare raw passwords.
create_access_token bundles user info (we'll pass {"sub": user.email}) plus an expiry into a JWT, signed with SECRET_KEY. Anyone can read a JWT's contents (it's just base64), but they can't forge a valid signature without the key — that's what makes it trustworthy.
decode_access_token verifies the signature and expiry; returns None if invalid/expired/tampered.
'''
