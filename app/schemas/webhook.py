from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class WebhookCreate(BaseModel):
    url: AnyHttpUrl
    events: list[str] = Field(default_factory=lambda: ["release.*"], min_length=1, max_length=25)


class WebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime


class WebhookCreated(WebhookRead):
    secret: str
