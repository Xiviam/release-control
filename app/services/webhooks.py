import hashlib
import hmac
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.webhook import WebhookEndpoint


def event_matches(patterns: list[str], event_type: str) -> bool:
    for pattern in patterns:
        if pattern == "*" or pattern == event_type:
            return True
        if pattern.endswith(".*") and event_type.startswith(pattern[:-1]):
            return True
    return False


def canonical_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def sign_payload(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def list_webhooks(session: AsyncSession, project_id: UUID) -> list[WebhookEndpoint]:
    result = await session.scalars(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.project_id == project_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return list(result)


async def delete_webhook(session: AsyncSession, *, project_id: UUID, endpoint_id: UUID) -> None:
    endpoint = await session.get(WebhookEndpoint, endpoint_id)
    if not endpoint or endpoint.project_id != project_id:
        raise NotFoundError("Webhook endpoint not found")
    await session.delete(endpoint)
