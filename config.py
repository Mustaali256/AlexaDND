"""Loads settings from .env into a single Config object."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
COOKIE_DIR = BASE_DIR / ".alexa_cookies"


@dataclass(frozen=True)
class Config:
    amazon_url: str
    amazon_email: str
    amazon_password: str
    amazon_otp_secret: str
    device_name: str
    cookie_dir: Path


def load_config() -> Config:
    load_dotenv(BASE_DIR / ".env")

    def require(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(
                f"Missing required setting {name}. Copy .env.example to .env and fill it in."
            )
        return value

    # alexapy writes its session cookie file under a ".storage" subfolder of
    # outputpath (this normally already exists as part of Home Assistant's
    # config dir, which is what alexapy is usually run inside). It doesn't
    # create the file's parent directory itself, and silently swallows the
    # resulting OSError, so the session would otherwise "log in" successfully
    # but never actually get saved to disk.
    (COOKIE_DIR / ".storage").mkdir(parents=True, exist_ok=True)

    return Config(
        amazon_url=os.environ.get("AMAZON_URL", "amazon.com").strip(),
        amazon_email=require("AMAZON_EMAIL"),
        amazon_password=require("AMAZON_PASSWORD"),
        amazon_otp_secret=os.environ.get("AMAZON_OTP_SECRET", "").strip(),
        device_name=require("ALEXA_DEVICE_NAME"),
        cookie_dir=COOKIE_DIR,
    )
