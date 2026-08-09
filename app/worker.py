import asyncio
from datetime import UTC, datetime

import httpx
from celery import Celery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import DeliveryStatus, OutboxStatus, ReleaseStatus
from app.db.session import SessionLocal
from app.models.release import Release
from app.models.webhook import OutboxEvent, WebhookDelivery, WebhookEndpoint
from app.services.events import record_domain_event
from app.services.webhooks import canonical_payload, event_matches, sign_payload

settings = get_settings()
celery_app = Celery("release_control", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "activate-due-releases": {
            "task": "release_control.activate_due_releases",
            "schedule": 15.0,
        },
        "publish-outbox-events": {
            "task": "release_control.publish_outbox_events",
            "schedule": 10.0,
        },
    },
)


@celery_app.task(name="release_control.activate_due_releases")  # type: ignore[untyped-decorator]
def activate_due_releases() -> int:
    return asyncio.run(_activate_due_releases())


async def _activate_due_releases() -> int:
    async with SessionLocal() as session:
        releases = list(
            await session.scalars(
                select(Release)
                .where(
                    Release.status == ReleaseStatus.SCHEDULED,
                    Release.scheduled_at <= datetime.now(UTC),
                )
                .with_for_update(skip_locked=True)
                .limit(50)
            )
        )
        for release in releases:
            release.status = ReleaseStatus.DEPLOYING
            await record_domain_event(
                session,
                project_id=release.project_id,
                actor_id=None,
                action="release.deployment_started",
                entity_type="release",
                entity_id=release.id,
                payload={
                    "release_id": str(release.id),
                    "project_id": str(release.project_id),
                    "environment_id": str(release.environment_id),
                    "version": release.version,
                    "status": release.status.value,
                    "trigger": "scheduler",
                },
            )
        await session.commit()
        return len(releases)


@celery_app.task(name="release_control.publish_outbox_events")  # type: ignore[untyped-decorator]
def publish_outbox_events() -> int:
    return asyncio.run(_publish_outbox_events())


async def _publish_outbox_events() -> int:
    async with SessionLocal() as session:
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(OutboxEvent.created_at)
                .with_for_update(skip_locked=True)
                .limit(50)
            )
        )
        delivered_count = 0
        async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
            for event in events:
                success = await _publish_event(session, client, event)
                delivered_count += int(success)
        await session.commit()
        return delivered_count


async def _publish_event(
    session: AsyncSession,
    client: httpx.AsyncClient,
    event: OutboxEvent,
) -> bool:
    endpoints = list(
        await session.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.project_id == event.project_id,
                WebhookEndpoint.is_active.is_(True),
            )
        )
    )
    endpoints = [item for item in endpoints if event_matches(item.events, event.event_type)]

    envelope: dict[str, object] = {
        "id": str(event.id),
        "type": event.event_type,
        "created_at": event.created_at.isoformat(),
        "data": event.payload,
    }
    body = canonical_payload(envelope)
    all_succeeded = True

    for endpoint in endpoints:
        delivery = WebhookDelivery(
            event_id=event.id,
            endpoint_id=endpoint.id,
            status=DeliveryStatus.PENDING,
            attempt_count=1,
        )
        session.add(delivery)
        try:
            response = await client.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Release-Control-Event": event.event_type,
                    "X-Release-Control-Signature": sign_payload(endpoint.secret, body),
                    "X-Release-Control-Delivery": str(delivery.id),
                },
            )
            delivery.response_status = response.status_code
            response.raise_for_status()
            delivery.status = DeliveryStatus.DELIVERED
            delivery.delivered_at = datetime.now(UTC)
        except httpx.HTTPError as exc:
            all_succeeded = False
            delivery.status = DeliveryStatus.FAILED
            delivery.error = str(exc)[:2000]
            event.last_error = delivery.error

    event.attempts += 1
    if all_succeeded:
        event.status = OutboxStatus.PUBLISHED
        event.published_at = datetime.now(UTC)
    elif event.attempts >= 5:
        event.status = OutboxStatus.FAILED
    return all_succeeded
