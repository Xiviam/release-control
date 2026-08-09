from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.webhook import OutboxEvent


async def record_domain_event(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict[str, object],
) -> None:
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            event_metadata=payload,
        )
    )
    session.add(OutboxEvent(project_id=project_id, event_type=action, payload=payload))
