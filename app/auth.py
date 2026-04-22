"""Basit cookie tabanlı admin auth.

Production'da reverse proxy (Coolify Traefik) üstünden TLS sağlandığı varsayılır.
Tek kullanıcılı, küçük ekipler için yeterli. İleride OAuth eklenebilir.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse

from .config import settings

SESSION_COOKIE = "sc_session"


def _sign(value: str) -> str:
    mac = hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{mac}"


def _verify(token: str) -> bool:
    try:
        value, mac = token.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected) and value == "admin"


def make_session_token() -> str:
    return _sign("admin")


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    return bool(token) and _verify(token)


def require_auth(request: Request) -> Optional[RedirectResponse]:
    """Dependency-benzeri: yetkisiz ise login'e yönlendir."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


def generate_webhook_slug() -> str:
    return secrets.token_urlsafe(12)


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(16)
