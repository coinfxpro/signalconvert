"""Telegram Bot API wrapper — sendPhoto ve sendMessage."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx


class TelegramError(Exception):
    pass


async def send_photo(
    bot_token: str,
    chat_id: str,
    photo_path: Path,
    caption: str = "",
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
    timeout: float = 20.0,
) -> int:
    """Fotoğraf gönderir ve Telegram message_id döndürür."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    async with httpx.AsyncClient(timeout=timeout) as client:
        with open(photo_path, "rb") as f:
            files = {"photo": (photo_path.name, f, "image/png")}
            data = {
                "chat_id": chat_id,
                "caption": caption[:1024],
                "parse_mode": parse_mode,
            }
            if reply_markup is not None:
                import json as _json
                data["reply_markup"] = _json.dumps(reply_markup)
            resp = await client.post(url, data=data, files=files)
    _raise_on_error(resp)
    body = resp.json()
    return int(body["result"]["message_id"])


async def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    timeout: float = 15.0,
) -> int:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": parse_mode,
        })
    _raise_on_error(resp)
    body = resp.json()
    return int(body["result"]["message_id"])


async def verify_bot(bot_token: str, timeout: float = 10.0) -> dict:
    """Token doğrula; dönen bilgilerle bot hakkında meta getir."""
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
    _raise_on_error(resp)
    return resp.json().get("result", {})


def _raise_on_error(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise TelegramError(f"HTTP {resp.status_code}: {resp.text}")
    try:
        body = resp.json()
    except Exception as e:
        raise TelegramError(f"Geçersiz JSON: {e}")
    if not body.get("ok"):
        raise TelegramError(body.get("description", "unknown error"))
