"""TradingView webhook alıcısı.

POST /webhook/{slug}?secret=...  veya  /webhook/{slug}/{secret}

Gövde: TradingView'in alert JSON'u. Alanlar esnektir (payload.py'e bakın).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import select

from ..card_renderer import build_caption, render_to_file
from ..config import settings
from ..db import session_scope
from ..models import Bot, Message
from ..payload import parse_payload
from ..telegram import TelegramError, send_photo

router = APIRouter(tags=["webhook"])


@router.post("/webhook/{slug}")
async def webhook_with_query(slug: str, request: Request):
    secret = request.query_params.get("secret", "")
    return await _process(slug, secret, request)


@router.post("/webhook/{slug}/{secret}")
async def webhook_with_path(slug: str, secret: str, request: Request):
    return await _process(slug, secret, request)


async def _process(slug: str, secret: str, request: Request) -> JSONResponse:
    t0 = time.time()
    body_bytes = await request.body()
    raw_text = body_bytes.decode("utf-8", errors="replace")

    # Bot'u bul ve secret'ı doğrula
    with session_scope() as s:
        bot: Bot | None = s.exec(select(Bot).where(Bot.webhook_slug == slug)).first()
        if bot is None:
            raise HTTPException(status_code=404, detail="bot not found")
        if not bot.active:
            raise HTTPException(status_code=403, detail="bot disabled")
        if secret != bot.webhook_secret:
            raise HTTPException(status_code=403, detail="invalid secret")
        bot_id = bot.id
        token = bot.telegram_bot_token
        chat_id = bot.telegram_chat_id
        brand = (bot.brand_name or bot.name or "").strip()

    # Mesaj kaydı oluştur (önce pending)
    try:
        data = parse_payload(raw_text)
    except Exception as e:  # noqa: BLE001
        with session_scope() as s:
            m = Message(bot_id=bot_id, event_type="PARSE_ERROR", raw_payload=raw_text,
                        status="failed", error=f"parse: {e}")
            s.add(m)
            s.commit()
        raise HTTPException(status_code=400, detail=f"invalid payload: {e}")

    with session_scope() as s:
        msg = Message(
            bot_id=bot_id,
            event_type=data.event_type,
            symbol=data.symbol,
            raw_payload=raw_text,
            status="pending",
        )
        s.add(msg)
        s.commit()
        s.refresh(msg)
        msg_id = msg.id
        # Bot istatistiği
        bot_obj = s.get(Bot, bot_id)
        if bot_obj:
            bot_obj.total_received += 1
            s.add(bot_obj)
            s.commit()

    # Kart üret — bot'un brand/ismi kartta footer olarak yazılsın
    if brand and not data.footer:
        data.footer = brand
    img_rel = f"{bot_id}/{msg_id}.png"
    img_path: Path = settings.IMAGES_DIR / img_rel
    try:
        render_to_file(data, img_path)
    except Exception as e:  # noqa: BLE001
        _mark_failed(msg_id, f"render: {e}", t0)
        raise HTTPException(status_code=500, detail=f"render failed: {e}")

    caption = build_caption(data)

    # Telegram'a gönder
    try:
        tg_mid = await send_photo(
            bot_token=token,
            chat_id=chat_id,
            photo_path=img_path,
            caption=caption,
        )
    except TelegramError as e:
        _mark_failed(msg_id, f"telegram: {e}", t0, image_rel=img_rel, caption=caption)
        raise HTTPException(status_code=502, detail=f"telegram failed: {e}")

    # Başarı
    processing_ms = int((time.time() - t0) * 1000)
    with session_scope() as s:
        m = s.get(Message, msg_id)
        if m:
            m.status = "sent"
            m.telegram_message_id = tg_mid
            m.image_path = img_rel
            m.caption = caption
            m.processing_ms = processing_ms
            s.add(m)
        b = s.get(Bot, bot_id)
        if b:
            b.total_sent += 1
            s.add(b)
        s.commit()

    return JSONResponse({"ok": True, "message_id": tg_mid, "processing_ms": processing_ms})


def _mark_failed(msg_id: int, error: str, t0: float, image_rel: str | None = None,
                 caption: str | None = None) -> None:
    processing_ms = int((time.time() - t0) * 1000)
    with session_scope() as s:
        m = s.get(Message, msg_id)
        if m:
            m.status = "failed"
            m.error = error[:500]
            m.processing_ms = processing_ms
            if image_rel:
                m.image_path = image_rel
            if caption:
                m.caption = caption
            s.add(m)
        if m:
            b = s.get(Bot, m.bot_id)
            if b:
                b.total_failed += 1
                s.add(b)
        s.commit()
