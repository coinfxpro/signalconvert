"""Ortam değişkenlerinden konfigürasyonu yükle."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/signalconvert.db")
    IMAGES_DIR: Path = BASE_DIR / os.getenv("IMAGES_DIR", "data/images")
    DATA_DIR: Path = BASE_DIR / "data"
    FONTS_DIR: Path = BASE_DIR / "app" / "static" / "fonts"

    def __init__(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.IMAGES_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
