import argparse
import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


async def bootstrap_admin() -> None:
    settings = get_settings()
    email = settings.bootstrap_admin_email.lower()
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            return
        session.add(
            User(
                email=email,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=UserRole.ADMIN,
            )
        )
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Release Control maintenance commands")
    parser.add_argument("command", choices=["bootstrap-admin"])
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        asyncio.run(bootstrap_admin())


if __name__ == "__main__":
    main()
