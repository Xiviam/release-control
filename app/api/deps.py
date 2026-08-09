from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep, token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = UUID(str(payload["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired access token") from exc

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User is inactive or no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError("Your role cannot perform this action")
        return user

    return dependency
