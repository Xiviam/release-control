from collections.abc import Awaitable, Callable
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.models.audit import AuditEvent
from app.models.user import User
from app.models.webhook import OutboxEvent
from tests.conftest import auth_headers


async def create_project_environment(
    client: AsyncClient, owner: User, *, requires_approval: bool = True
) -> tuple[str, str]:
    project = await client.post(
        "/api/v1/projects",
        headers=auth_headers(owner),
        json={"name": "Checkout", "slug": "checkout", "description": "Checkout API"},
    )
    project_id = project.json()["id"]
    environment = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=auth_headers(owner),
        json={"name": "production", "requires_approval": requires_approval},
    )
    return project_id, environment.json()["id"]


async def create_release(
    client: AsyncClient, owner: User, project_id: str, environment_id: str
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/releases",
        headers={**auth_headers(owner), "Idempotency-Key": "checkout-v1.2.0-production"},
        json={
            "project_id": project_id,
            "environment_id": environment_id,
            "version": "v1.2.0",
            "artifact_uri": "ghcr.io/acme/checkout:v1.2.0",
            "commit_sha": "a1b2c3d4e5f67890",
            "changelog": "Add idempotent checkout",
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_full_release_lifecycle_and_idempotency(
    client: AsyncClient,
    session: AsyncSession,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    reviewer = await user_factory(UserRole.REVIEWER, "reviewer@example.com")
    admin = await user_factory(UserRole.ADMIN, "admin@example.com")
    project_id, environment_id = await create_project_environment(client, developer)
    release = await create_release(client, developer, project_id, environment_id)
    release_id = str(release["id"])
    assert release["status"] == "draft"

    replay = await client.post(
        "/api/v1/releases",
        headers={
            **auth_headers(developer),
            "Idempotency-Key": "checkout-v1.2.0-production",
        },
        json={
            "project_id": project_id,
            "environment_id": environment_id,
            "version": "v1.2.0",
            "artifact_uri": "ghcr.io/acme/checkout:v1.2.0",
            "commit_sha": "a1b2c3d4e5f67890",
            "changelog": "Add idempotent checkout",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == release_id

    submitted = await client.post(
        f"/api/v1/releases/{release_id}/submit",
        headers=auth_headers(developer),
        json={"comment": "Ready for review"},
    )
    assert submitted.json()["status"] == "pending_approval"

    developer_approval = await client.post(
        f"/api/v1/releases/{release_id}/approve",
        headers=auth_headers(developer),
        json={"comment": "I approve"},
    )
    assert developer_approval.status_code == 403

    approved = await client.post(
        f"/api/v1/releases/{release_id}/approve",
        headers=auth_headers(reviewer),
        json={"comment": "Checks passed"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == str(reviewer.id)

    deploying = await client.post(
        f"/api/v1/releases/{release_id}/deploy",
        headers=auth_headers(admin),
        json={"comment": "Starting production deployment"},
    )
    assert deploying.json()["status"] == "deploying"

    deployed = await client.post(
        f"/api/v1/releases/{release_id}/complete",
        headers=auth_headers(admin),
        json={"comment": "Health checks passed"},
    )
    assert deployed.json()["status"] == "deployed"
    assert deployed.json()["deployed_at"] is not None

    rolled_back = await client.post(
        f"/api/v1/releases/{release_id}/rollback",
        headers=auth_headers(admin),
        json={"comment": "Rollback drill"},
    )
    assert rolled_back.json()["status"] == "rolled_back"
    assert rolled_back.json()["lock_version"] > 1

    actions = list(
        await session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.project_id == UUID(project_id))
            .order_by(AuditEvent.created_at)
        )
    )
    assert "release.created" in actions
    assert "release.approved" in actions
    assert "release.deployed" in actions
    assert "release.rolled_back" in actions
    audit_count = await session.scalar(select(func.count(AuditEvent.id)))
    outbox_count = await session.scalar(select(func.count(OutboxEvent.id)))
    assert audit_count == outbox_count


async def test_environment_without_gate_auto_approves(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    project_id, environment_id = await create_project_environment(
        client, developer, requires_approval=False
    )
    release = await create_release(client, developer, project_id, environment_id)
    submitted = await client.post(
        f"/api/v1/releases/{release['id']}/submit",
        headers=auth_headers(developer),
        json={"comment": "Preview deployment"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "approved"
