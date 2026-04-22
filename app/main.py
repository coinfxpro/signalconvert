"""SignalConvert — TradingView → Pillow kart → Telegram sendPhoto."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routes import dashboard, webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="SignalConvert", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(webhook.router)
app.include_router(dashboard.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}
