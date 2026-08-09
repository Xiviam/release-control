import secrets
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import WebhookCreate, WebhookCreated, WebhookRead
from app.services.projects import get_project, require_project_manager
from app.services.webhooks import delete_webhook, list_webhooks

router = APIRouter(prefix="/projects/{project_id}/webhooks", tags=["Webhooks"])


@router.post("", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    project_id: UUID,
    payload: WebhookCreate,
    session: SessionDep,
    user: CurrentUser,
) -> WebhookEndpoint:
    project = await get_project(session, project_id)
    require_project_manager(project, user)
    endpoint = WebhookEndpoint(
        project_id=project_id,
        url=str(payload.url),
        events=payload.events,
        secret=secrets.token_urlsafe(32),
    )
    session.add(endpoint)
    await session.commit()
    await session.refresh(endpoint)
    return endpoint


@router.get("", response_model=list[WebhookRead])
async def get_webhooks(
    project_id: UUID, session: SessionDep, _: CurrentUser
) -> list[WebhookEndpoint]:
    await get_project(session, project_id)
    return await list_webhooks(session, project_id)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_webhook(
    project_id: UUID,
    endpoint_id: UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    project = await get_project(session, project_id)
    require_project_manager(project, user)
    await delete_webhook(session, project_id=project_id, endpoint_id=endpoint_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
