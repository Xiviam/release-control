from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID
    event_metadata: dict[str, object]
    created_at: datetime
