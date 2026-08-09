from httpx import AsyncClient


async def test_health_dashboard_and_request_id(client: AsyncClient) -> None:
    health = await client.get("/health", headers={"X-Request-ID": "smoke-test"})
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health.headers["X-Request-ID"] == "smoke-test"

    dashboard = await client.get("/")
    assert dashboard.status_code == 200
    assert "Release Control" in dashboard.text
