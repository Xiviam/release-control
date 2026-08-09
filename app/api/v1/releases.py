from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.core.enums import ApprovalDecision, ReleaseStatus
from app.models.release import Release
from app.schemas.release import ReleaseCreate, ReleaseRead, ScheduleRequest, TransitionRequest
from app.services.releases import (
    cancel_release,
    create_release,
    finish_deployment,
    get_release,
    list_releases,
    review_release,
    rollback_release,
    schedule_release,
    start_deployment,
    submit_release,
)

router = APIRouter(prefix="/releases", tags=["Releases"])


async def _commit_and_reload(session: SessionDep, release: Release) -> Release:
    release_id = release.id
    await session.commit()
    return await get_release(session, release_id)


@router.post("", response_model=ReleaseRead, status_code=status.HTTP_201_CREATED)
async def post_release(
    payload: ReleaseCreate,
    response: Response,
    session: SessionDep,
    user: CurrentUser,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=120)] = None,
) -> Release:
    release, replayed = await create_release(
        session,
        payload=payload,
        idempotency_key=idempotency_key,
        actor=user,
    )
    if replayed:
        response.status_code = status.HTTP_200_OK
        return release
    return await _commit_and_reload(session, release)


@router.get("", response_model=list[ReleaseRead])
async def get_releases(
    session: SessionDep,
    _: CurrentUser,
    project_id: UUID | None = None,
    release_status: ReleaseStatus | None = Query(default=None, alias="status"),
) -> list[Release]:
    return await list_releases(session, project_id=project_id, status=release_status)


@router.get("/{release_id}", response_model=ReleaseRead)
async def get_release_by_id(release_id: UUID, session: SessionDep, _: CurrentUser) -> Release:
    return await get_release(session, release_id)


@router.post("/{release_id}/submit", response_model=ReleaseRead)
async def submit(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await submit_release(
        session, release_id=release_id, actor=user, comment=payload.comment
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/approve", response_model=ReleaseRead)
async def approve(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await review_release(
        session,
        release_id=release_id,
        actor=user,
        decision=ApprovalDecision.APPROVED,
        comment=payload.comment,
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/reject", response_model=ReleaseRead)
async def reject(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await review_release(
        session,
        release_id=release_id,
        actor=user,
        decision=ApprovalDecision.REJECTED,
        comment=payload.comment,
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/schedule", response_model=ReleaseRead)
async def schedule(
    release_id: UUID,
    payload: ScheduleRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await schedule_release(
        session,
        release_id=release_id,
        actor=user,
        scheduled_at=payload.scheduled_at,
        comment=payload.comment,
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/deploy", response_model=ReleaseRead)
async def deploy(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await start_deployment(
        session, release_id=release_id, actor=user, comment=payload.comment
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/complete", response_model=ReleaseRead)
async def complete(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await finish_deployment(
        session,
        release_id=release_id,
        actor=user,
        succeeded=True,
        comment=payload.comment,
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/fail", response_model=ReleaseRead)
async def fail(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await finish_deployment(
        session,
        release_id=release_id,
        actor=user,
        succeeded=False,
        comment=payload.comment,
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/rollback", response_model=ReleaseRead)
async def rollback(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await rollback_release(
        session, release_id=release_id, actor=user, comment=payload.comment
    )
    return await _commit_and_reload(session, release)


@router.post("/{release_id}/cancel", response_model=ReleaseRead)
async def cancel(
    release_id: UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Release:
    release = await cancel_release(
        session, release_id=release_id, actor=user, comment=payload.comment
    )
    return await _commit_and_reload(session, release)
