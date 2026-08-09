from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.core.enums import UserRole
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest, Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> User:
    existing = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise ConflictError("A user with this email already exists")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=UserRole.DEVELOPER,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/token", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    user = await session.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise AuthenticationError("Incorrect email or password")
    if not user.is_active:
        raise AuthenticationError("User is inactive")
    return Token(access_token=create_access_token(str(user.id), {"role": user.role.value}))


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: SessionDep,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> User:
    existing = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise ConflictError("A user with this email already exists")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
