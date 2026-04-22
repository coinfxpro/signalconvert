"""Web UI dashboard: login, bot listesi, bot ekle/düzenle/sil, mesaj geçmişi, preview."""
from __future__ import annotations

import json as _json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..auth import (
    SESSION_COOKIE,
    generate_webhook_secret,
    generate_webhook_slug,
    is_authenticated,
    make_session_token,
)
from ..card_renderer import render_to_file
from ..config import settings
from ..db import get_session
from ..models import Bot, Message
from ..payload import parse_payload
from ..telegram import TelegramError, verify_bot

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _guard(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="login required")


# ---------------------------------------------------------------- LOGIN
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def do_login(request: Request, password: str = Form(...)):
    if password != settings.ADMIN_PASSWORD:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Parola hatalı."},
            status_code=401,
        )
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, make_session_token(),
                    httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


@router.post("/logout")
def do_logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---------------------------------------------------------------- DASHBOARD
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    bots = session.exec(select(Bot).order_by(Bot.created_at.desc())).all()
    recent = session.exec(select(Message).order_by(Message.created_at.desc()).limit(15)).all()

    # Özet sayaçları
    total_sent = sum(b.total_sent for b in bots)
    total_recv = sum(b.total_received for b in bots)
    total_fail = sum(b.total_failed for b in bots)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "bots": bots,
        "recent": recent,
        "total_sent": total_sent,
        "total_recv": total_recv,
        "total_fail": total_fail,
        "public_base_url": settings.PUBLIC_BASE_URL,
    })


# ---------------------------------------------------------------- BOT CRUD
@router.get("/bots/new", response_class=HTMLResponse)
def new_bot_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("bot_form.html", {
        "request": request, "bot": None, "error": None,
    })


@router.post("/bots/new")
async def create_bot(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    telegram_bot_token: str = Form(...),
    telegram_chat_id: str = Form(...),
    session: Session = Depends(get_session),
):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    # Token doğrula
    try:
        await verify_bot(telegram_bot_token)
    except TelegramError as e:
        return templates.TemplateResponse("bot_form.html", {
            "request": request, "bot": None,
            "error": f"Bot token doğrulanamadı: {e}",
            "form": {"name": name, "description": description,
                     "telegram_bot_token": telegram_bot_token,
                     "telegram_chat_id": telegram_chat_id},
        }, status_code=400)

    bot = Bot(
        name=name.strip(),
        description=description.strip() or None,
        telegram_bot_token=telegram_bot_token.strip(),
        telegram_chat_id=telegram_chat_id.strip(),
        webhook_slug=generate_webhook_slug(),
        webhook_secret=generate_webhook_secret(),
    )
    session.add(bot)
    session.commit()
    session.refresh(bot)
    return RedirectResponse(url=f"/bots/{bot.id}", status_code=303)


@router.get("/bots/{bot_id}", response_class=HTMLResponse)
def bot_detail(bot_id: int, request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    bot = session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="bot not found")
    messages = session.exec(
        select(Message).where(Message.bot_id == bot_id).order_by(Message.created_at.desc()).limit(50)
    ).all()
    webhook_url = f"{settings.PUBLIC_BASE_URL}/webhook/{bot.webhook_slug}?secret={bot.webhook_secret}"
    return templates.TemplateResponse("bot_detail.html", {
        "request": request, "bot": bot, "messages": messages,
        "webhook_url": webhook_url,
        "public_base_url": settings.PUBLIC_BASE_URL,
    })


@router.post("/bots/{bot_id}/toggle")
def toggle_bot(bot_id: int, request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    bot = session.get(Bot, bot_id)
    if bot:
        bot.active = not bot.active
        session.add(bot)
        session.commit()
    return RedirectResponse(url=f"/bots/{bot_id}", status_code=303)


@router.post("/bots/{bot_id}/rotate-secret")
def rotate_secret(bot_id: int, request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    bot = session.get(Bot, bot_id)
    if bot:
        bot.webhook_secret = generate_webhook_secret()
        session.add(bot)
        session.commit()
    return RedirectResponse(url=f"/bots/{bot_id}", status_code=303)


@router.post("/bots/{bot_id}/delete")
def delete_bot(bot_id: int, request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    bot = session.get(Bot, bot_id)
    if bot:
        session.delete(bot)
        session.commit()
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------- TEST
@router.post("/bots/{bot_id}/test")
async def test_send(bot_id: int, request: Request, session: Session = Depends(get_session)):
    """Demo bir 'DİP ALIM' kartı üretip Telegram'a gönderir."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    from ..card_renderer import build_caption  # local import to avoid cycle cost
    from ..telegram import send_photo
    from ..payload import parse_payload as _pp

    bot = session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="bot not found")

    demo = {
        "event": "DIP_AL", "symbol": "TESTX", "subtitle": "15M %3 Kâr Al",
        "price": 23.24, "entry": 23.24, "target": 23.47, "stop": 22.89,
        "rr": 0.66, "confidence": 74.9, "change_pct": 0.0,
    }
    data = _pp(demo)
    from pathlib import Path as _P
    img_rel = f"{bot.id}/test-preview.png"
    img_path: _P = settings.IMAGES_DIR / img_rel
    render_to_file(data, img_path)
    caption = build_caption(data) + " <i>(test)</i>"

    try:
        await send_photo(bot.telegram_bot_token, bot.telegram_chat_id, img_path, caption)
        bot.total_sent += 1
    except TelegramError as e:
        bot.total_failed += 1
        session.add(bot); session.commit()
        raise HTTPException(status_code=502, detail=f"telegram failed: {e}")
    session.add(bot); session.commit()
    return RedirectResponse(url=f"/bots/{bot.id}", status_code=303)


# ---------------------------------------------------------------- PREVIEW
@router.get("/preview", response_class=HTMLResponse)
def preview_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("preview.html", {"request": request})


@router.post("/preview/render")
def preview_render(request: Request, payload: str = Form(...)):
    if not is_authenticated(request):
        raise HTTPException(status_code=401)
    try:
        data = parse_payload(payload)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    out = settings.IMAGES_DIR / "_preview.png"
    render_to_file(data, out)
    return FileResponse(out, media_type="image/png")


# ---------------------------------------------------------------- MESSAGES
@router.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request, session: Session = Depends(get_session),
                  bot_id: int | None = None, status: str | None = None):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    q = select(Message).order_by(Message.created_at.desc()).limit(200)
    if bot_id:
        q = select(Message).where(Message.bot_id == bot_id).order_by(Message.created_at.desc()).limit(200)
    if status:
        q = select(Message).where(Message.status == status).order_by(Message.created_at.desc()).limit(200)
    items = session.exec(q).all()
    bots = session.exec(select(Bot)).all()
    return templates.TemplateResponse("messages.html", {
        "request": request, "items": items, "bots": bots,
        "filter_bot": bot_id, "filter_status": status,
    })


@router.get("/messages/{msg_id}", response_class=HTMLResponse)
def message_detail(msg_id: int, request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    m = session.get(Message, msg_id)
    if not m:
        raise HTTPException(status_code=404)
    bot = session.get(Bot, m.bot_id)
    try:
        parsed = _json.dumps(_json.loads(m.raw_payload), indent=2, ensure_ascii=False)
    except Exception:
        parsed = m.raw_payload
    return templates.TemplateResponse("message_detail.html", {
        "request": request, "m": m, "bot": bot, "parsed": parsed,
    })


@router.get("/images/{path:path}")
def serve_image(path: str):
    p = settings.IMAGES_DIR / path
    if not p.exists() or not str(p.resolve()).startswith(str(settings.IMAGES_DIR.resolve())):
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type="image/png")
