from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import UserRole
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.project import Environment, Project
from app.models.user import User
from app.schemas.project import EnvironmentCreate, ProjectCreate
from app.services.events import record_domain_event


async def create_project(session: AsyncSession, *, payload: ProjectCreate, actor: User) -> Project:
    existing = await session.scalar(select(Project).where(Project.slug == payload.slug))
    if existing:
        raise ConflictError("A project with this slug already exists")

    project = Project(**payload.model_dump(), created_by=actor.id)
    session.add(project)
    await session.flush()
    await record_domain_event(
        session,
        project_id=project.id,
        actor_id=actor.id,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
        payload={"project_id": str(project.id), "slug": project.slug},
    )
    return project


async def get_project(session: AsyncSession, project_id: UUID) -> Project:
    project = await session.scalar(
        select(Project).where(Project.id == project_id).options(selectinload(Project.environments))
    )
    if not project:
        raise NotFoundError("Project not found")
    return project


def require_project_manager(project: Project, actor: User) -> None:
    if project.created_by != actor.id and actor.role is not UserRole.ADMIN:
        raise ForbiddenError("Only the project owner or an admin can modify this project")


async def create_environment(
    session: AsyncSession,
    *,
    project: Project,
    payload: EnvironmentCreate,
    actor: User,
) -> Environment:
    require_project_manager(project, actor)
    existing = await session.scalar(
        select(Environment).where(
            Environment.project_id == project.id, Environment.name == payload.name
        )
    )
    if existing:
        raise ConflictError("This environment already exists in the project")

    environment = Environment(project_id=project.id, **payload.model_dump())
    session.add(environment)
    await session.flush()
    await record_domain_event(
        session,
        project_id=project.id,
        actor_id=actor.id,
        action="environment.created",
        entity_type="environment",
        entity_id=environment.id,
        payload={
            "project_id": str(project.id),
            "environment_id": str(environment.id),
            "name": environment.name,
            "requires_approval": environment.requires_approval,
        },
    )
    return environment


async def list_projects(session: AsyncSession) -> list[Project]:
    result = await session.scalars(select(Project).order_by(Project.created_at.desc()))
    return list(result)
