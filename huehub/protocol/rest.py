"""Async HTTPS REST client for the Hue Bridge CLIP API v2.

All requests automatically inject the ``hue-application-key`` header.
Responses are validated and errors from the bridge payload are surfaced as
:class:`~huehub.exceptions.ApiError`.
"""

import logging

import httpx

from huehub.exceptions import ApiError, AuthError, BridgeUnavailableError

log = logging.getLogger(__name__)

_CLIP_V2 = "/clip/v2"


class HueRestClient:
    """Thin wrapper around :class:`httpx.AsyncClient` for the CLIP v2 API.

    Args:
        host: Bridge IP address or hostname.
        application_key: Application key for the ``hue-application-key`` header.
        client: Configured ``httpx.AsyncClient`` (owns its lifecycle).
    """

    def __init__(
        self, host: str, application_key: str, client: httpx.AsyncClient
    ) -> None:
        self._host = host
        self._application_key = application_key
        self._client = client
        self._base_url = f"https://{host}{_CLIP_V2}"

    # ------------------------------------------------------------------
    # Public CRUD methods
    # ------------------------------------------------------------------

    async def get(self, path: str) -> list[dict]:
        """Send a GET request and return the ``data`` array.

        Args:
            path: URL path relative to ``/clip/v2``, e.g. ``"/resource/light"``.

        Returns:
            List of resource dicts from the bridge response.

        Raises:
            BridgeUnavailableError: If the bridge cannot be reached.
            AuthError: If the response is HTTP 401.
            ApiError: If the bridge body contains errors.
        """
        return await self._request("GET", path, body=None)

    async def put(self, path: str, body: dict) -> list[dict]:
        """Send a PUT request with a JSON body.

        Args:
            path: URL path relative to ``/clip/v2``.
            body: JSON payload.

        Returns:
            List of resource dicts from the bridge response.
        """
        return await self._request("PUT", path, body=body)

    async def post(self, path: str, body: dict) -> list[dict]:
        """Send a POST request with a JSON body.

        Args:
            path: URL path relative to ``/clip/v2``.
            body: JSON payload.

        Returns:
            List of resource dicts from the bridge response.
        """
        return await self._request("POST", path, body=body)

    async def delete(self, path: str) -> list[dict]:
        """Send a DELETE request.

        Args:
            path: URL path relative to ``/clip/v2``.

        Returns:
            List of resource dicts from the bridge response.
        """
        return await self._request("DELETE", path, body=None)

    # ------------------------------------------------------------------
    # Authentication helper (uses /api, not /clip/v2)
    # ------------------------------------------------------------------

    async def post_auth(self, body: dict) -> dict:
        """POST to the legacy ``/api`` endpoint for app-key registration.

        Args:
            body: Registration payload, e.g.
                ``{"devicetype": "huehub#client", "generateclientkey": true}``.

        Returns:
            The raw JSON list item dict (either ``success`` or ``error`` key).

        Raises:
            BridgeUnavailableError: If the bridge cannot be reached.
        """
        url = f"https://{self._host}/api"
        try:
            response = await self._client.post(
                url,
                json=body,
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and data:
                return data[0]
            return {}
        except httpx.ConnectError as exc:
            raise BridgeUnavailableError(
                f"Cannot reach bridge at {self._host}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise BridgeUnavailableError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"hue-application-key": self._application_key}

    async def _request(self, method: str, path: str, body: dict | None) -> list[dict]:
        url = f"{self._base_url}{path}"
        headers = self._auth_headers()
        try:
            if body is not None:
                response = await self._client.request(
                    method, url, json=body, headers=headers
                )
            else:
                response = await self._client.request(method, url, headers=headers)
        except httpx.ConnectError as exc:
            raise BridgeUnavailableError(
                f"Cannot reach bridge at {self._host}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise BridgeUnavailableError(
                f"Request to bridge at {self._host} timed out"
            ) from exc

        if response.status_code == 401:
            raise AuthError(
                "Invalid or missing application key (HTTP 401). "
                "Run 'hue setup' to register."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BridgeUnavailableError(
                f"Bridge returned HTTP {response.status_code}"
            ) from exc

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: httpx.Response) -> list[dict]:
        """Extract the ``data`` list and surface any bridge-level errors.

        Args:
            response: Completed HTTP response with a JSON body.

        Returns:
            The ``data`` array from the bridge response.

        Raises:
            ApiError: If the bridge body contains ``errors``.
        """
        payload = response.json()
        if errors := payload.get("errors", []):
            first = errors[0]
            raise ApiError(
                first.get("description", "Unknown API error"),
                error_type=first.get("type", 0),
            )
        return payload.get("data", [])
