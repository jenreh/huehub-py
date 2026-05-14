"""Custom exceptions for the huehub library."""


class HuehubError(Exception):
    """Base exception for all huehub errors."""


class BridgeUnavailableError(HuehubError):
    """Bridge is not reachable on the network."""


class AuthError(HuehubError):
    """Authentication failed – invalid or missing application key."""


class LinkButtonNotPressedError(AuthError):
    """Bridge link button was not pressed in time during registration."""


class ResourceNotFoundError(HuehubError):
    """No resource with the given name or UUID exists on the bridge.

    Args:
        resource_type: Type of resource (e.g. ``"light"``, ``"room"``).
        identifier: The name or UUID that was not found.
    """

    def __init__(self, resource_type: str, identifier: str) -> None:
        self.resource_type = resource_type
        self.identifier = identifier
        super().__init__(f"No {resource_type} found: {identifier!r}")


class AmbiguousNameError(HuehubError):
    """Multiple resources match the given name.

    Args:
        resource_type: Type of resource (e.g. ``"light"``).
        name: The ambiguous name that was searched.
        candidates: Display strings of the matching resources.
    """

    def __init__(self, resource_type: str, name: str, candidates: list[str]) -> None:
        self.resource_type = resource_type
        self.name = name
        self.candidates = candidates
        super().__init__(
            f"Ambiguous {resource_type} name {name!r}; "
            f"candidates: {', '.join(candidates)}"
        )


class TlsError(HuehubError):
    """TLS/SSL-level error when connecting to the bridge."""


class CertificateError(TlsError):
    """Bridge certificate could not be extracted or is invalid."""


class ApiError(HuehubError):
    """The bridge API returned an error payload.

    Args:
        description: Human-readable error description from the bridge.
        error_type: Numeric error type code from the bridge response.
    """

    def __init__(self, description: str, error_type: int = 0) -> None:
        self.error_type = error_type
        super().__init__(description)
