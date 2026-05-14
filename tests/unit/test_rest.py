"""Unit tests for HueRestClient."""

import httpx
import pytest
from pytest_httpx import HTTPXMock

from huehub.exceptions import ApiError, AuthError, BridgeUnavailableError
from huehub.protocol.rest import HueRestClient

pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)

_HOST = "192.168.1.1"
_KEY = "test-app-key"
_BASE = f"https://{_HOST}/clip/v2"


@pytest.fixture
def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(verify=False, timeout=5)


@pytest.fixture
def rest(http_client: httpx.AsyncClient) -> HueRestClient:
    return HueRestClient(_HOST, _KEY, http_client)


class TestGet:
    async def test_get_returns_data(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/resource/light",
            json={"data": [{"id": "abc", "type": "light"}], "errors": []},
        )
        result = await rest.get("/resource/light")
        assert result[0]["id"] == "abc"

    async def test_get_raises_auth_error_on_401(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/resource/light",
            status_code=401,
        )
        with pytest.raises(AuthError):
            await rest.get("/resource/light")

    async def test_get_raises_api_error_on_bridge_error(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/resource/light",
            json={"data": [], "errors": [{"description": "Not authorized", "type": 1}]},
        )
        with pytest.raises(ApiError):
            await rest.get("/resource/light")

    async def test_get_raises_on_http_error(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/resource/light",
            status_code=500,
        )
        with pytest.raises(BridgeUnavailableError):
            await rest.get("/resource/light")


class TestPut:
    async def test_put_sends_body(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="PUT",
            url=f"{_BASE}/resource/light/abc",
            json={"data": [{"rid": "abc", "rtype": "light"}], "errors": []},
        )
        result = await rest.put("/resource/light/abc", {"on": {"on": True}})
        assert result[0]["rid"] == "abc"


class TestPostAuth:
    async def test_returns_success(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=f"https://{_HOST}/api",
            json=[{"success": {"username": "new-key", "clientkey": "ck"}}],
        )
        result = await rest.post_auth({"devicetype": "test"})
        assert result["success"]["username"] == "new-key"

    async def test_returns_error_dict(
        self, rest: HueRestClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="POST",
            url=f"https://{_HOST}/api",
            json=[{"error": {"type": 101, "description": "link button"}}],
        )
        result = await rest.post_auth({"devicetype": "test"})
        assert result["error"]["type"] == 101
