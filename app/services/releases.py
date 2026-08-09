from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ApprovalDecision, ReleaseStatus, UserRole
from app.core.exceptions import ConflictError, ForbiddenError, InvalidTransitionError, NotFoundError
from app.models.project import Environment, Project
from app.models.release import Release, ReleaseApproval
from app.models.user import User
from app.schemas.release import ReleaseCreate
from app.services.events import record_domain_event


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def get_release(
    session: AsyncSession, release_id: UUID, *, for_update: bool = False
) -> Release:
    statement = (
        select(Release)
        .where(Release.id == release_id)
        .options(selectinload(Release.approvals), selectinload(Release.environment))
    )
    if for_update:
        statement = statement.with_for_update()
    release = await session.scalar(statement)
    if not release:
        raise NotFoundError("Release not found")
    return release


async def list_releases(
    session: AsyncSession,
    *,
    project_id: UUID | None = None,
    status: ReleaseStatus | None = None,
) -> list[Release]:
    statement = select(Release).options(
        selectinload(Release.approvals), selectinload(Release.environment)
    )
    if project_id:
        statement = statement.where(Release.project_id == project_id)
    if status:
        statement = statement.where(Release.status == status)
    result = await session.scalars(statement.order_by(Release.created_at.desc()))
    return list(result.unique())


async def create_release(
    session: AsyncSession,
    *,
    payload: ReleaseCreate,
    idempotency_key: str | None,
    actor: User,
) -> tuple[Release, bool]:
    if idempotency_key:
        existing = await session.scalar(
            select(Release)
            .where(
                Release.project_id == payload.project_id,
                Release.idempotency_key == idempotency_key,
            )
            .options(selectinload(Release.approvals), selectinload(Release.environment))
        )
        if existing:
            return existing, True

    project = await session.get(Project, payload.project_id)
    if not project:
        raise NotFoundError("Project not found")
    if project.created_by != actor.id and actor.role is not UserRole.ADMIN:
        raise ForbiddenError("Only the project owner or an admin can create releases")
    environment = await session.get(Environment, payload.environment_id)
    if not environment or environment.project_id != project.id:
        raise NotFoundError("Environment not found in this project")

    duplicate = await session.scalar(
        select(Release).where(
            Release.project_id == payload.project_id,
            Release.environment_id == payload.environment_id,
            Release.version == payload.version,
        )
    )
    if duplicate:
        raise ConflictError("This version already exists in the selected environment")

    release = Release(
        **payload.model_dump(),
        idempotency_key=idempotency_key,
        created_by=actor.id,
    )
    session.add(release)
    await session.flush()
    await record_domain_event(
        session,
        project_id=release.project_id,
        actor_id=actor.id,
        action="release.created",
        entity_type="release",
        entity_id=release.id,
        payload=_release_payload(release),
    )
    return release, False


def _release_payload(release: Release, comment: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "release_id": str(release.id),
        "project_id": str(release.project_id),
        "environment_id": str(release.environment_id),
        "version": release.version,
        "status": release.status.value,
        "commit_sha": release.commit_sha,
    }
    if comment:
        payload["comment"] = comment
    if release.scheduled_at:
        payload["scheduled_at"] = release.scheduled_at.isoformat()
    return payload


def _require_creator_or_admin(release: Release, actor: User) -> None:
    if release.created_by != actor.id and actor.role is not UserRole.ADMIN:
        raise ForbiddenError("Only the release creator or an admin can perform this action")


def _require_role(actor: User, *roles: UserRole) -> None:
    if actor.role not in roles:
        raise ForbiddenError("Your role cannot perform this release transition")


def _ensure_status(release: Release, *expected: ReleaseStatus) -> None:
    if release.status not in expected:
        allowed = ", ".join(item.value for item in expected)
        raise InvalidTransitionError(
            f"Release is '{release.status.value}', expected one of: {allowed}"
        )


async def _record_release_transition(
    session: AsyncSession,
    *,
    release: Release,
    actor_id: UUID | None,
    action: str,
    comment: str | None = None,
) -> None:
    await record_domain_event(
        session,
        project_id=release.project_id,
        actor_id=actor_id,
        action=action,
        entity_type="release",
        entity_id=release.id,
        payload=_release_payload(release, comment),
    )


async def submit_release(
    session: AsyncSession, *, release_id: UUID, actor: User, comment: str | None
) -> Release:
    release = await get_release(session, release_id, for_update=True)
    _require_creator_or_admin(release, actor)
    _ensure_status(release, ReleaseStatus.DRAFT, ReleaseStatus.REJECTED)

    if release.environment.requires_approval:
        release.status = ReleaseStatus.PENDING_APPROVAL
        action = "release.submitted"
    else:
        release.status = ReleaseStatus.APPROVED
        action = "release.auto_approved"
    await _record_release_transition(
        session, release=release, actor_id=actor.id, action=action, comment=comment
    )
    await session.flush()
    return release


async def review_release(
    session: AsyncSession,
    *,
    release_id: UUID,
    actor: User,
    decision: ApprovalDecision,
    comment: str | None,
) -> Release:
    _require_role(actor, UserRole.REVIEWER, UserRole.ADMIN)
    release = await get_release(session, release_id, for_update=True)
    _ensure_status(release, ReleaseStatus.PENDING_APPROVAL)
    if release.created_by == actor.id and actor.role is not UserRole.ADMIN:
        raise ForbiddenError("Reviewers cannot approve their own releases")

    release.status = (
        ReleaseStatus.APPROVED if decision is ApprovalDecision.APPROVED else ReleaseStatus.REJECTED
    )
    if decision is ApprovalDecision.APPROVED:
        release.approved_by = actor.id
    session.add(
        ReleaseApproval(
            release_id=release.id,
            reviewer_id=actor.id,
            decision=decision,
            comment=comment,
        )
    )
    await _record_release_transition(
        session,
        release=release,
        actor_id=actor.id,
        action=f"release.{decision.value}",
        comment=comment,
    )
    await session.flush()
    return release


async def schedule_release(
    session: AsyncSession,
    *,
    release_id: UUID,
    actor: User,
    scheduled_at: datetime,
    comment: str | None,
) -> Release:
    release = await get_release(session, release_id, for_update=True)
    _require_creator_or_admin(release, actor)
    _ensure_status(release, ReleaseStatus.APPROVED)
    if scheduled_at.astimezone(UTC) <= datetime.now(UTC):
        raise ConflictError("scheduled_at must be in the future")

    release.status = ReleaseStatus.SCHEDULED
    release.scheduled_at = scheduled_at.astimezone(UTC)
    await _record_release_transition(
        session,
        release=release,
        actor_id=actor.id,
        action="release.scheduled",
        comment=comment,
    )
    await session.flush()
    return release


async def start_deployment(
    session: AsyncSession,
    *,
    release_id: UUID,
    actor: User,
    comment: str | None,
) -> Release:
    _require_role(actor, UserRole.ADMIN)
    release = await get_release(session, release_id, for_update=True)
    _ensure_status(release, ReleaseStatus.APPROVED, ReleaseStatus.SCHEDULED)
    if (
        release.status is ReleaseStatus.SCHEDULED
        and release.scheduled_at
        and _as_utc(release.scheduled_at) > datetime.now(UTC)
    ):
        raise ConflictError("This release is scheduled for a future time")

    release.status = ReleaseStatus.DEPLOYING
    await _record_release_transition(
        session,
        release=release,
        actor_id=actor.id,
        action="release.deployment_started",
        comment=comment,
    )
    await session.flush()
    return release


async def finish_deployment(
    session: AsyncSession,
    *,
    release_id: UUID,
    actor: User,
    succeeded: bool,
    comment: str | None,
) -> Release:
    _require_role(actor, UserRole.ADMIN)
    release = await get_release(session, release_id, for_update=True)
    _ensure_status(release, ReleaseStatus.DEPLOYING)

    release.status = ReleaseStatus.DEPLOYED if succeeded else ReleaseStatus.FAILED
    if succeeded:
        release.deployed_at = datetime.now(UTC)
    action = "release.deployed" if succeeded else "release.failed"
    await _record_release_transition(
        session, release=release, actor_id=actor.id, action=action, comment=comment
    )
    await session.flush()
    return release


async def rollback_release(
    session: AsyncSession, *, release_id: UUID, actor: User, comment: str | None
) -> Release:
    _require_role(actor, UserRole.ADMIN)
    release = await get_release(session, release_id, for_update=True)
    _ensure_status(release, ReleaseStatus.DEPLOYED)
    release.status = ReleaseStatus.ROLLED_BACK
    await _record_release_transition(
        session,
        release=release,
        actor_id=actor.id,
        action="release.rolled_back",
        comment=comment,
    )
    await session.flush()
    return release


async def cancel_release(
    session: AsyncSession, *, release_id: UUID, actor: User, comment: str | None
) -> Release:
    release = await get_release(session, release_id, for_update=True)
    _require_creator_or_admin(release, actor)
    _ensure_status(
        release,
        ReleaseStatus.DRAFT,
        ReleaseStatus.PENDING_APPROVAL,
        ReleaseStatus.APPROVED,
        ReleaseStatus.REJECTED,
        ReleaseStatus.SCHEDULED,
    )
    release.status = ReleaseStatus.CANCELLED
    await _record_release_transition(
        session,
        release=release,
        actor_id=actor.id,
        action="release.cancelled",
        comment=comment,
    )
    await session.flush()
    return release
