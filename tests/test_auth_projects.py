from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.enums import UserRole
from app.models.user import User
from tests.conftest import auth_headers


async def test_register_login_and_current_user(client: AsyncClient) -> None:
    registration = await client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "password": "strong-password"},
    )
    assert registration.status_code == 201
    assert registration.json()["role"] == "developer"

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "password": "strong-password"},
    )
    assert duplicate.status_code == 409

    login = await client.post(
        "/api/v1/auth/token",
        data={"username": "dev@example.com", "password": "strong-password"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "dev@example.com"


async def test_project_owner_controls_environments(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    owner = await user_factory(UserRole.DEVELOPER, "owner@example.com")
    stranger = await user_factory(UserRole.DEVELOPER, "stranger@example.com")

    created = await client.post(
        "/api/v1/projects",
        headers=auth_headers(owner),
        json={"name": "Payments", "slug": "payments", "description": "Core API"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    forbidden = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=auth_headers(stranger),
        json={"name": "production", "requires_approval": True},
    )
    assert forbidden.status_code == 403

    environment = await client.post(
        f"/api/v1/projects/{project_id}/environments",
        headers=auth_headers(owner),
        json={"name": "production", "requires_approval": True},
    )
    assert environment.status_code == 201
    assert environment.json()["name"] == "production"

    projects = await client.get("/api/v1/projects", headers=auth_headers(owner))
    assert projects.status_code == 200
    assert [item["slug"] for item in projects.json()] == ["payments"]


async def test_admin_can_create_reviewer(
    client: AsyncClient,
    user_factory: Callable[[UserRole, str], Awaitable[User]],
) -> None:
    admin = await user_factory(UserRole.ADMIN, "admin@example.com")
    created = await client.post(
        "/api/v1/auth/users",
        headers=auth_headers(admin),
        json={
            "email": "reviewer@example.com",
            "password": "strong-password",
            "role": "reviewer",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "reviewer"


async def test_invalid_credentials_and_token_return_401(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "password": "strong-password"},
    )
    wrong_password = await client.post(
        "/api/v1/auth/token",
        data={"username": "dev@example.com", "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401
    assert wrong_password.headers["www-authenticate"] == "Bearer"

    invalid_token = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer definitely-not-a-jwt"}
    )
    assert invalid_token.status_code == 401
