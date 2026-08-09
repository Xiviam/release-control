from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient

from app.core.enums import UserRole
from app.models.user import User
from tests.conftest import auth_headers
from tests.test_release_workflow import create_project_environment, create_release


async def test_invalid_transition_returns_structured_conflict(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    admin = await user_factory(UserRole.ADMIN, "admin@example.com")
    project_id, environment_id = await create_project_environment(client, developer)
    release = await create_release(client, developer, project_id, environment_id)

    response = await client.post(
        f"/api/v1/releases/{release['id']}/deploy",
        headers=auth_headers(admin),
        json={"comment": None},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_RELEASE_TRANSITION"


async def test_rejection_resubmission_and_future_schedule(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    reviewer = await user_factory(UserRole.REVIEWER, "reviewer@example.com")
    project_id, environment_id = await create_project_environment(client, developer)
    release = await create_release(client, developer, project_id, environment_id)
    release_id = str(release["id"])

    await client.post(
        f"/api/v1/releases/{release_id}/submit",
        headers=auth_headers(developer),
        json={"comment": None},
    )
    rejected = await client.post(
        f"/api/v1/releases/{release_id}/reject",
        headers=auth_headers(reviewer),
        json={"comment": "Missing migration plan"},
    )
    assert rejected.json()["status"] == "rejected"

    await client.post(
        f"/api/v1/releases/{release_id}/submit",
        headers=auth_headers(developer),
        json={"comment": "Migration plan added"},
    )
    await client.post(
        f"/api/v1/releases/{release_id}/approve",
        headers=auth_headers(reviewer),
        json={"comment": "Approved"},
    )
    scheduled_at = datetime.now(UTC) + timedelta(hours=2)
    scheduled = await client.post(
        f"/api/v1/releases/{release_id}/schedule",
        headers=auth_headers(developer),
        json={"scheduled_at": scheduled_at.isoformat(), "comment": "Maintenance window"},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "scheduled"

    too_early = await client.post(
        f"/api/v1/releases/{release_id}/deploy",
        headers=auth_headers(await user_factory(UserRole.ADMIN, "admin@example.com")),
        json={"comment": None},
    )
    assert too_early.status_code == 409


async def test_reviewer_cannot_approve_own_release(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    reviewer = await user_factory(UserRole.REVIEWER, "reviewer@example.com")
    project_id, environment_id = await create_project_environment(client, reviewer)
    release = await create_release(client, reviewer, project_id, environment_id)
    await client.post(
        f"/api/v1/releases/{release['id']}/submit",
        headers=auth_headers(reviewer),
        json={"comment": None},
    )
    response = await client.post(
        f"/api/v1/releases/{release['id']}/approve",
        headers=auth_headers(reviewer),
        json={"comment": "Self approval"},
    )
    assert response.status_code == 403


async def test_failed_deployment_can_be_filtered_and_fetched(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    admin = await user_factory(UserRole.ADMIN, "admin@example.com")
    project_id, environment_id = await create_project_environment(
        client, developer, requires_approval=False
    )
    release = await create_release(client, developer, project_id, environment_id)
    release_id = str(release["id"])
    await client.post(
        f"/api/v1/releases/{release_id}/submit",
        headers=auth_headers(developer),
        json={"comment": None},
    )
    await client.post(
        f"/api/v1/releases/{release_id}/deploy",
        headers=auth_headers(admin),
        json={"comment": None},
    )
    failed = await client.post(
        f"/api/v1/releases/{release_id}/fail",
        headers=auth_headers(admin),
        json={"comment": "Readiness probe failed"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"

    listing = await client.get(
        f"/api/v1/releases?project_id={project_id}&status=failed",
        headers=auth_headers(developer),
    )
    assert [item["id"] for item in listing.json()] == [release_id]
    fetched = await client.get(f"/api/v1/releases/{release_id}", headers=auth_headers(developer))
    assert fetched.status_code == 200
    missing = await client.get(f"/api/v1/releases/{uuid4()}", headers=auth_headers(developer))
    assert missing.status_code == 404
