"""Unit tests for exception classes."""

from huehub.exceptions import (
    AmbiguousNameError,
    ApiError,
    AuthError,
    BridgeUnavailableError,
    CertificateError,
    HuehubError,
    LinkButtonNotPressedError,
    ResourceNotFoundError,
    TlsError,
)


class TestExceptionHierarchy:
    def test_base(self) -> None:
        e = HuehubError("base error")
        assert isinstance(e, Exception)

    def test_bridge_unavailable(self) -> None:
        e = BridgeUnavailableError("no host")
        assert isinstance(e, HuehubError)

    def test_auth_error(self) -> None:
        e = AuthError("bad key")
        assert isinstance(e, HuehubError)

    def test_link_button(self) -> None:
        e = LinkButtonNotPressedError("timeout")
        assert isinstance(e, AuthError)

    def test_tls_error(self) -> None:
        e = TlsError("ssl fail")
        assert isinstance(e, HuehubError)

    def test_certificate_error(self) -> None:
        e = CertificateError("no cert")
        assert isinstance(e, TlsError)


class TestResourceNotFoundError:
    def test_fields(self) -> None:
        e = ResourceNotFoundError("light", "Desk Lamp")
        assert e.resource_type == "light"
        assert e.identifier == "Desk Lamp"
        assert "Desk Lamp" in str(e)
        assert "light" in str(e)

    def test_is_huehub_error(self) -> None:
        e = ResourceNotFoundError("room", "Kitchen")
        assert isinstance(e, HuehubError)


class TestAmbiguousNameError:
    def test_fields(self) -> None:
        e = AmbiguousNameError("light", "Lamp", ["Desk Lamp", "Floor Lamp"])
        assert e.resource_type == "light"
        assert e.name == "Lamp"
        assert "Desk Lamp" in e.candidates
        assert "Floor Lamp" in e.candidates
        assert "Lamp" in str(e)

    def test_message_includes_candidates(self) -> None:
        e = AmbiguousNameError("light", "x", ["a", "b"])
        msg = str(e)
        assert "a" in msg
        assert "b" in msg


class TestApiError:
    def test_default_error_type(self) -> None:
        e = ApiError("some description")
        assert str(e) == "some description"
        assert e.error_type == 0

    def test_custom_error_type(self) -> None:
        e = ApiError("resource not found", error_type=404)
        assert e.error_type == 404

    def test_is_huehub_error(self) -> None:
        e = ApiError("msg")
        assert isinstance(e, HuehubError)
