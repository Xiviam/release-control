from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.enums import UserRole
from app.models.user import User
from tests.conftest import auth_headers
from tests.test_release_workflow import create_project_environment


async def test_webhook_create_list_and_delete(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    project_id, _ = await create_project_environment(client, developer)

    created = await client.post(
        f"/api/v1/projects/{project_id}/webhooks",
        headers=auth_headers(developer),
        json={"url": "https://example.com/hooks", "events": ["release.*"]},
    )
    assert created.status_code == 201
    assert created.json()["secret"]
    endpoint_id = created.json()["id"]

    listing = await client.get(
        f"/api/v1/projects/{project_id}/webhooks", headers=auth_headers(developer)
    )
    assert listing.status_code == 200
    assert listing.json()[0]["url"] == "https://example.com/hooks"
    assert "secret" not in listing.json()[0]

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/webhooks/{endpoint_id}",
        headers=auth_headers(developer),
    )
    assert deleted.status_code == 204

    listing = await client.get(
        f"/api/v1/projects/{project_id}/webhooks", headers=auth_headers(developer)
    )
    assert listing.json() == []


async def test_cannot_delete_webhook_through_another_project(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    developer = await user_factory(UserRole.DEVELOPER, "developer@example.com")
    first_id, _ = await create_project_environment(client, developer)
    created = await client.post(
        f"/api/v1/projects/{first_id}/webhooks",
        headers=auth_headers(developer),
        json={"url": "https://example.com/hooks", "events": ["release.*"]},
    )

    second = await client.post(
        "/api/v1/projects",
        headers=auth_headers(developer),
        json={"name": "Second", "slug": "second", "description": None},
    )
    response = await client.delete(
        f"/api/v1/projects/{second.json()['id']}/webhooks/{created.json()['id']}",
        headers=auth_headers(developer),
    )
    assert response.status_code == 404
