from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli, worker
from app.core.enums import OutboxStatus, ReleaseStatus, UserRole
from app.core.security import verify_password
from app.models.project import Environment, Project
from app.models.release import Release
from app.models.user import User
from app.models.webhook import OutboxEvent, WebhookDelivery, WebhookEndpoint


class SessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


class SessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def __call__(self) -> SessionContext:
        return SessionContext(self.session)


class SuccessfulResponse:
    status_code = 202

    def raise_for_status(self) -> None:
        return None


class SuccessfulClient:
    def __init__(self, **_: object) -> None:
        self.requests: list[tuple[str, bytes, dict[str, str]]] = []

    async def __aenter__(self) -> "SuccessfulClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(
        self, url: str, *, content: bytes, headers: dict[str, str]
    ) -> SuccessfulResponse:
        self.requests.append((url, content, headers))
        return SuccessfulResponse()


class FailingClient(SuccessfulClient):
    async def post(
        self, url: str, *, content: bytes, headers: dict[str, str]
    ) -> SuccessfulResponse:
        del content, headers
        raise httpx.ConnectError("endpoint unavailable", request=httpx.Request("POST", url))


async def create_release_records(
    session: AsyncSession,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> tuple[Project, Release]:
    user = await user_factory(UserRole.DEVELOPER, "worker@example.com")
    project = Project(name="Worker", slug="worker", created_by=user.id)
    session.add(project)
    await session.flush()
    environment = Environment(project_id=project.id, name="production", requires_approval=True)
    session.add(environment)
    await session.flush()
    release = Release(
        project_id=project.id,
        environment_id=environment.id,
        version="v2.0.0",
        artifact_uri="ghcr.io/acme/worker:v2.0.0",
        commit_sha="abcdef1234567890",
        status=ReleaseStatus.SCHEDULED,
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        created_by=user.id,
    )
    session.add(release)
    await session.commit()
    return project, release


async def test_scheduler_activates_release_and_worker_delivers_webhook(
    session: AsyncSession,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
    monkeypatch,
) -> None:
    project, release = await create_release_records(session, user_factory)
    endpoint = WebhookEndpoint(
        project_id=project.id,
        url="https://example.com/releases",
        secret="webhook-secret",
        events=["release.*"],
    )
    session.add(endpoint)
    await session.commit()

    monkeypatch.setattr(worker, "SessionLocal", SessionFactory(session))
    activated = await worker._activate_due_releases()
    assert activated == 1
    await session.refresh(release)
    assert release.status is ReleaseStatus.DEPLOYING

    monkeypatch.setattr(worker.httpx, "AsyncClient", SuccessfulClient)
    published = await worker._publish_outbox_events()
    assert published == 1

    outbox = await session.scalar(select(OutboxEvent))
    assert outbox is not None
    assert outbox.status is OutboxStatus.PUBLISHED
    delivery_count = await session.scalar(select(func.count(WebhookDelivery.id)))
    assert delivery_count == 1


async def test_worker_stops_retrying_after_five_failures(
    session: AsyncSession,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
    monkeypatch,
) -> None:
    project, _ = await create_release_records(session, user_factory)
    endpoint = WebhookEndpoint(
        project_id=project.id,
        url="https://example.com/unavailable",
        secret="webhook-secret",
        events=["release.failed"],
    )
    event = OutboxEvent(
        project_id=project.id,
        event_type="release.failed",
        payload={"release_id": "demo"},
        attempts=4,
    )
    session.add_all([endpoint, event])
    await session.commit()

    monkeypatch.setattr(worker, "SessionLocal", SessionFactory(session))
    monkeypatch.setattr(worker.httpx, "AsyncClient", FailingClient)
    published = await worker._publish_outbox_events()
    assert published == 0
    await session.refresh(event)
    assert event.status is OutboxStatus.FAILED
    assert event.attempts == 5
    assert "endpoint unavailable" in str(event.last_error)


async def test_bootstrap_admin_is_idempotent(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(cli, "SessionLocal", SessionFactory(session))
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            bootstrap_admin_email="bootstrap@example.com",
            bootstrap_admin_password="bootstrap-password",
        ),
    )
    await cli.bootstrap_admin()
    await cli.bootstrap_admin()

    users = list(await session.scalars(select(User)))
    assert len(users) == 1
    assert users[0].role is UserRole.ADMIN
    assert verify_password("bootstrap-password", users[0].password_hash)
