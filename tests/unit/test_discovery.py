"""Unit tests for the discovery module."""

import httpx
import pytest
from pytest_httpx import HTTPXMock

from huehub import discovery

pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)


class TestDiscoverCloud:
    async def test_returns_bridges(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://discovery.meethue.com/",
            json=[
                {"internalipaddress": "192.168.1.1", "id": "ecb5faaabbcc"},
                {"internalipaddress": "192.168.1.2", "id": "ecb5faddee00"},
            ],
        )
        client = httpx.AsyncClient(timeout=5)
        results = await discovery.discover_cloud(client=client)
        await client.aclose()
        assert len(results) == 2
        hosts = {r["host"] for r in results}
        assert "192.168.1.1" in hosts
        assert "192.168.1.2" in hosts

    async def test_skips_entries_without_ip(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://discovery.meethue.com/",
            json=[
                {"internalipaddress": "", "id": "abc"},
                {"internalipaddress": "10.0.0.1", "id": "def"},
            ],
        )
        client = httpx.AsyncClient(timeout=5)
        results = await discovery.discover_cloud(client=client)
        await client.aclose()
        assert len(results) == 1
        assert results[0]["host"] == "10.0.0.1"

    async def test_http_error_returns_empty(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://discovery.meethue.com/",
            status_code=500,
        )
        client = httpx.AsyncClient(timeout=5)
        results = await discovery.discover_cloud(client=client)
        await client.aclose()
        assert results == []

    async def test_creates_own_client_if_none(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://discovery.meethue.com/",
            json=[{"internalipaddress": "172.16.0.1", "id": "xyz"}],
        )
        # No client passed → creates its own
        results = await discovery.discover_cloud()
        assert len(results) == 1


class TestDiscover:
    async def test_skips_mdns_and_hostname_when_disabled(
        self, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://discovery.meethue.com/",
            json=[{"internalipaddress": "10.0.0.5", "id": "abcdef123456"}],
        )
        results = await discovery.discover(
            use_mdns=False, use_hostname=False, use_cloud=True
        )
        assert len(results) == 1
        assert results[0]["host"] == "10.0.0.5"

    async def test_returns_empty_when_all_disabled(self) -> None:
        results = await discovery.discover(
            use_mdns=False, use_hostname=False, use_cloud=False
        )
        assert results == []

    async def test_stops_at_first_result(
        self, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If hostname resolves, cloud is not called."""
        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **kw: [(None, None, None, None, ("192.168.0.10", 443))],
        )
        results = await discovery.discover(
            use_mdns=False, use_hostname=True, use_cloud=True
        )
        # Should return hostname result; cloud mock not needed
        assert len(results) == 1
        assert results[0]["host"] == "192.168.0.10"


class TestDiscoverHostname:
    async def test_returns_resolved_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **kw: [(None, None, None, None, ("192.168.1.99", 443))],
        )
        results = await discovery.discover_hostname()
        assert len(results) == 1
        assert results[0]["host"] == "192.168.1.99"

    async def test_returns_empty_on_os_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import socket

        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **kw: (_ for _ in ()).throw(OSError())
        )
        results = await discovery.discover_hostname()
        assert results == []
