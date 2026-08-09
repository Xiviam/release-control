from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.audit import AuditEvent
from app.models.project import Environment, Project
from app.schemas.audit import AuditEventRead
from app.schemas.project import EnvironmentCreate, EnvironmentRead, ProjectCreate, ProjectRead
from app.services.projects import (
    create_environment,
    create_project,
    get_project,
    list_projects,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def post_project(payload: ProjectCreate, session: SessionDep, user: CurrentUser) -> Project:
    project = await create_project(session, payload=payload, actor=user)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def get_projects(session: SessionDep, _: CurrentUser) -> list[Project]:
    return await list_projects(session)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project_by_id(project_id: UUID, session: SessionDep, _: CurrentUser) -> Project:
    return await get_project(session, project_id)


@router.post(
    "/{project_id}/environments",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_environment(
    project_id: UUID,
    payload: EnvironmentCreate,
    session: SessionDep,
    user: CurrentUser,
) -> Environment:
    project = await get_project(session, project_id)
    environment = await create_environment(session, project=project, payload=payload, actor=user)
    await session.commit()
    await session.refresh(environment)
    return environment


@router.get("/{project_id}/environments", response_model=list[EnvironmentRead])
async def get_environments(
    project_id: UUID, session: SessionDep, _: CurrentUser
) -> list[Environment]:
    await get_project(session, project_id)
    result = await session.scalars(
        select(Environment)
        .where(Environment.project_id == project_id)
        .order_by(Environment.created_at)
    )
    return list(result)


@router.get("/{project_id}/audit", response_model=list[AuditEventRead])
async def get_audit_log(
    project_id: UUID,
    session: SessionDep,
    _: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEvent]:
    await get_project(session, project_id)
    result = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.project_id == project_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return list(result)
