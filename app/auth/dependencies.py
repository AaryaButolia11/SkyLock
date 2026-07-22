from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth.security import decode_access_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    email = payload.get("sub")
    if email is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
'''
get_current_admin depends on get_current_user — so it first verifies the JWT and fetches the user (same as before), then adds one more check: is is_admin true? If not, 403 Forbidden. Any route that needs admin-only access just uses Depends(get_current_admin) instead of Depends(get_current_user).
'''


'''
OAuth2PasswordBearer tells FastAPI to expect a Authorization: Bearer <token> header and auto-generates the "Authorize" button in /docs. get_current_user is a dependency you'll drop into any route that needs to know who's calling it — e.g. POST /bookings will use this to know which user is booking, without trusting a user_id sent in the request body (never trust the client to tell you who they are).
'''
