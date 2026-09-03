"""Thin wrapper around alexapy for logging in and toggling Do Not Disturb."""
from __future__ import annotations

import logging
from typing import Any, Optional

from alexapy import AlexaAPI, AlexaLogin

from config import Config

logger = logging.getLogger(__name__)


class _DeviceHandle:
    """Minimal stand-in for the device object alexapy.AlexaAPI expects.

    AlexaAPI is normally driven by Home Assistant's alexa_media_player
    integration, which passes it a rich AlexaClient object. Standalone, all
    we have is the raw dict from AlexaAPI.get_devices(), so this wraps it
    with just the attributes AlexaAPI.set_dnd_state() actually reads.
    """

    def __init__(self, raw: dict[str, Any]):
        self.device_serial_number: str = raw["serialNumber"]
        self._device_type: str = raw["deviceType"]


class AlexaDndController:
    """Logs in with a saved session and toggles DND on one Echo device."""

    def __init__(self, config: Config):
        self._device_name = config.device_name
        self.login = AlexaLogin(
            url=config.amazon_url,
            email=config.amazon_email,
            password=config.amazon_password,
            outputpath=lambda filename: str(config.cookie_dir / filename),
            otp_secret=config.amazon_otp_secret,
            oauth_login=True,
        )
        self._device: Optional[_DeviceHandle] = None

    async def ensure_logged_in(self) -> None:
        """Log in using the cookie/session saved by setup_login.py.

        This should not require any interactive input; if it does, the
        saved session has expired and setup_login.py must be re-run.
        """
        cookies = await self.login.load_cookie()
        await self.login.login(cookies=cookies)
        if not (self.login.status and self.login.status.get("login_successful")):
            raise RuntimeError(
                "Alexa login did not complete automatically "
                f"(status={self.login.status}). Re-run setup_login.py."
            )

    async def _get_device(self) -> _DeviceHandle:
        if self._device is not None:
            return self._device

        devices = await AlexaAPI.get_devices(self.login) or []
        for device in devices:
            if device.get("accountName") == self._device_name:
                self._device = _DeviceHandle(device)
                return self._device

        available = ", ".join(d.get("accountName", "?") for d in devices) or "(none found)"
        raise RuntimeError(
            f"Device '{self._device_name}' not found on this account. "
            f"Available devices: {available}"
        )

    async def set_dnd(self, enabled: bool) -> None:
        device = await self._get_device()
        api = AlexaAPI(device, self.login)
        await api.set_dnd_state(enabled)
        logger.info("Set DND=%s on '%s'", enabled, self._device_name)

    async def close(self) -> None:
        await self.login.close()
