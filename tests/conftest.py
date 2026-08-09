import os
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET"] = "test-secret-that-is-not-used-in-production"

from app import models  # noqa: F401
from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db_session:
        yield db_session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def user_factory(
    session: AsyncSession,
) -> Callable[[UserRole, str], Awaitable[User]]:
    async def factory(role: UserRole, email: str) -> User:
        user = User(
            email=email,
            password_hash=hash_password("strong-password"),
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    return factory


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(str(user.id), {"role": user.role.value})
    return {"Authorization": f"Bearer {token}"}
