"""SQLModel veri modelleri: Bot ve Message."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Bot(SQLModel, table=True):
    """Her bot = 1 Telegram token + 1 chat_id + benzersiz webhook slug."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="Kullanıcı dostu isim, örn. 'Dip Alım Botu'")
    description: Optional[str] = Field(default=None)
    telegram_bot_token: str
    telegram_chat_id: str
    webhook_slug: str = Field(index=True, unique=True, description="Webhook URL path (rastgele üretilir)")
    webhook_secret: str = Field(description="Ek güvenlik tokeni; URL'de query veya path'te tutulur")
    active: bool = Field(default=True)
    card_style: str = Field(default="default", description="Kart şablonu seçimi (ileride genişletilebilir)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # İstatistik sayaçları (denormalize, hızlı okuma için)
    total_received: int = Field(default=0)
    total_sent: int = Field(default=0)
    total_failed: int = Field(default=0)


class Message(SQLModel, table=True):
    """Gelen webhook ve giden Telegram mesajının kaydı."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Gelen veri
    event_type: str = Field(default="UNKNOWN", index=True, description="DIP_AL, TP1, TP2, STOP, TRAILING, PUSU vb.")
    symbol: Optional[str] = Field(default=None, index=True)
    raw_payload: str = Field(description="TradingView'den gelen ham JSON")

    # İşleme sonucu
    status: str = Field(default="pending", index=True, description="pending / sent / failed")
    error: Optional[str] = Field(default=None)
    telegram_message_id: Optional[int] = Field(default=None)
    image_path: Optional[str] = Field(default=None, description="Üretilen kart PNG (relative path)")
    caption: Optional[str] = Field(default=None)
    processing_ms: Optional[int] = Field(default=None)
