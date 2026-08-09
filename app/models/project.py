from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.release import Release
    from app.models.webhook import WebhookEndpoint


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    environments: Mapped[list[Environment]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    releases: Mapped[list[Release]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="raise"
    )
    webhooks: Mapped[list[WebhookEndpoint]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="raise"
    )


class Environment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped[Project] = relationship(back_populates="environments")
    releases: Mapped[list[Release]] = relationship(back_populates="environment", lazy="raise")
