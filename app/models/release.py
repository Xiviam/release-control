from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ApprovalDecision, ReleaseStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Environment, Project


class Release(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("project_id", "environment_id", "version"),
        UniqueConstraint("project_id", "idempotency_key"),
    )

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    environment_id: Mapped[UUID] = mapped_column(ForeignKey("environments.id", ondelete="RESTRICT"))
    version: Mapped[str] = mapped_column(String(80))
    artifact_uri: Mapped[str] = mapped_column(String(500))
    commit_sha: Mapped[str] = mapped_column(String(40))
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReleaseStatus] = mapped_column(
        Enum(
            ReleaseStatus,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            length=32,
        ),
        default=ReleaseStatus.DRAFT,
        index=True,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    deployed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="releases")
    environment: Mapped[Environment] = relationship(back_populates="releases", lazy="selectin")
    approvals: Mapped[list[ReleaseApproval]] = relationship(
        back_populates="release", cascade="all, delete-orphan", lazy="selectin"
    )

    __mapper_args__: dict[str, object] = {"version_id_col": lock_version}  # noqa: RUF012


class ReleaseApproval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "release_approvals"

    release_id: Mapped[UUID] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"))
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision: Mapped[ApprovalDecision] = mapped_column(
        Enum(
            ApprovalDecision,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            length=16,
        )
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    release: Mapped[Release] = relationship(back_populates="approvals")
