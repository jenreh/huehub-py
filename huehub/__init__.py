"""huehub – Local control of the Philips Hue Bridge via CLIP API v2."""

from huehub.client import HueBridgeClient
from huehub.config import HueConfig, load_config
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
from huehub.models import (
    AllResources,
    BridgeInfo,
    ColorResult,
    ContactSensor,
    Device,
    EntertainmentZone,
    GroupedLight,
    HueEvent,
    Light,
    LightLevelSensor,
    MotionSensor,
    Room,
    Scene,
    TemperatureSensor,
    Zone,
)

__all__ = [  # noqa: RUF022
    "HueBridgeClient",
    "HueConfig",
    "load_config",
    # Exceptions
    "HuehubError",
    "AmbiguousNameError",
    "ApiError",
    "AuthError",
    "BridgeUnavailableError",
    "CertificateError",
    "LinkButtonNotPressedError",
    "ResourceNotFoundError",
    "TlsError",
    # Models
    "AllResources",
    "BridgeInfo",
    "ColorResult",
    "ContactSensor",
    "Device",
    "EntertainmentZone",
    "GroupedLight",
    "HueEvent",
    "Light",
    "LightLevelSensor",
    "MotionSensor",
    "Room",
    "Scene",
    "TemperatureSensor",
    "Zone",
]
