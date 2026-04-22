"""TradingView webhook JSON payload'unu CardData'ya çevirir.

TradingView'den esnek bir JSON beklendiğinden eksik alanlar tolere edilir.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .card_renderer import CardData


EVENT_ALIASES = {
    "DIP_AL": "DIP_AL", "DIP": "DIP_AL", "AL": "DIP_AL",
    "SIGNAL": "SIGNAL", "YENI_SINYAL": "SIGNAL",
    "TP1": "TP1", "HEDEF1": "TP1", "HEDEF_1": "TP1",
    "TP2": "TP2", "HEDEF2": "TP2", "HEDEF_2": "TP2",
    "STOP": "STOP", "STOP_LOSS": "STOP",
    "TRAILING": "TRAILING", "TRAIL": "TRAILING",
    "PUSU": "PUSU",
}


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str):
            v = v.replace(",", ".").replace("%", "").replace("TL", "").strip()
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_payload(raw: str | Dict[str, Any]) -> CardData:
    """Ham JSON veya dict'ten CardData üret."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Ham text geldiyse minimal kart göster
            return CardData(event_type="SIGNAL", symbol="UNKNOWN", subtitle=raw[:60])
    else:
        data = raw

    et_raw = str(data.get("event") or data.get("event_type") or data.get("type") or "SIGNAL").upper()
    event_type = EVENT_ALIASES.get(et_raw, et_raw)

    return CardData(
        event_type=event_type,
        symbol=str(data.get("symbol") or data.get("ticker") or "—"),
        subtitle=str(data.get("subtitle") or data.get("strategy") or ""),
        price=_f(data.get("price") or data.get("close")),
        change_pct=_f(data.get("change_pct") or data.get("change")),
        entry=_f(data.get("entry") or data.get("giris")),
        target=_f(data.get("target") or data.get("tp") or data.get("tp1") or data.get("hedef")),
        stop=_f(data.get("stop") or data.get("sl")),
        exit_price=_f(data.get("exit") or data.get("cikis") or data.get("exit_price")),
        rr=_f(data.get("rr") or data.get("r_r")),
        confidence=_f(data.get("confidence") or data.get("guven")),
        kar_pct=_f(data.get("kar_pct") or data.get("pnl") or data.get("kar")),
        duration=str(data.get("duration") or "") or None,
        opened_at=str(data.get("opened_at") or "") or None,
        closed_at=str(data.get("closed_at") or "") or None,
        footer=str(data.get("footer") or "SignalConvert"),
    )
