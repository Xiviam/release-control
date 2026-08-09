from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DeliveryStatus, OutboxStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WebhookEndpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_endpoints"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(255))
    events: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)

    project = relationship("Project", back_populates="webhooks")


class OutboxEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outbox_events"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(
            OutboxStatus,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            length=16,
        ),
        default=OutboxStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WebhookDelivery(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "webhook_deliveries"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="CASCADE"), index=True
    )
    endpoint_id: Mapped[UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            length=16,
        ),
        default=DeliveryStatus.PENDING,
    )
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
