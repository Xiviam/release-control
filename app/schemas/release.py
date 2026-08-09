from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ApprovalDecision, ReleaseStatus


class ReleaseCreate(BaseModel):
    project_id: UUID
    environment_id: UUID
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,79}$")
    artifact_uri: str = Field(min_length=3, max_length=500)
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{7,40}$")
    changelog: str | None = Field(default=None, max_length=10000)


class ReleaseApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reviewer_id: UUID
    decision: ApprovalDecision
    comment: str | None
    created_at: datetime


class ReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    environment_id: UUID
    version: str
    artifact_uri: str
    commit_sha: str
    changelog: str | None
    status: ReleaseStatus
    scheduled_at: datetime | None
    deployed_at: datetime | None
    created_by: UUID
    approved_by: UUID | None
    lock_version: int
    created_at: datetime
    updated_at: datetime
    approvals: list[ReleaseApprovalRead] = Field(default_factory=list)


class TransitionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ScheduleRequest(BaseModel):
    scheduled_at: datetime
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone")
        return value
