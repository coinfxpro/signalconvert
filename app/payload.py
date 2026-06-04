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
    "ALGO_TARAMA": "ALGO_TARAMA", "ALGO": "ALGO_TARAMA",
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

    def _s(key: str, *more: str) -> str:
        for k in (key, *more):
            v = data.get(k)
            if v is not None and str(v).strip() != "":
                return str(v)
        return ""

    return CardData(
        event_type=event_type,
        symbol=str(data.get("symbol") or data.get("ticker") or "—"),
        subtitle=_s("subtitle", "strategy"),
        price=_f(data.get("price") or data.get("close")),
        change_pct=_f(data.get("change_pct") or data.get("change")),
        entry=_f(data.get("entry") or data.get("giris")),
        target=_f(data.get("target") or data.get("tp") or data.get("tp1") or data.get("hedef")),
        target2=_f(data.get("target2") or data.get("tp2") or data.get("hedef2")),
        stop=_f(data.get("stop") or data.get("sl")),
        exit_price=_f(data.get("exit") or data.get("cikis") or data.get("exit_price")),
        rr=_f(data.get("rr") or data.get("r_r")),
        confidence=_f(data.get("confidence") or data.get("guven")),
        kar_pct=_f(data.get("kar_pct") or data.get("pnl") or data.get("kar")),
        duration=_s("duration") or None,
        opened_at=_s("opened_at") or None,
        closed_at=_s("closed_at") or None,
        footer=_s("footer", "brand"),  # boşsa render tarafında BRAND_NAME fallback
        # Zengin kriter/istatistik alanları
        gunluk_skor=data.get("gunluk_skor") if isinstance(data.get("gunluk_skor"), int) else _f(data.get("gunluk_skor")),
        gunluk_etiket=_s("gunluk_etiket", "gunluk_gun") or None,
        gunluk_kriterler=_s("gunluk_kriterler") or None,
        canli_skor=data.get("canli_skor") if isinstance(data.get("canli_skor"), int) else _f(data.get("canli_skor")),
        canli_kriterler=_s("canli_kriterler") or None,
        giris_skor=data.get("giris_skor") if isinstance(data.get("giris_skor"), int) else _f(data.get("giris_skor")),
        giris_kriterler=_s("giris_kriterler") or None,
        atr_daily=_f(data.get("atr_daily") or data.get("atr")),
        basari_oran=_f(data.get("basari_oran") or data.get("win_rate")),
        kazanc=int(data["kazanc"]) if isinstance(data.get("kazanc"), (int, float)) else None,
        kayip=int(data["kayip"]) if isinstance(data.get("kayip"), (int, float)) else None,
        signal_tag=(_s("signal_tag", "tag") or None),
        # AlgoTarama alanları
        periyot=_s("periyot") or None,
        rsi=_f(data.get("rsi")),
        sma_500=_f(data.get("sma_500")),
        sma_200=_f(data.get("sma_200")),
        sma_50=_f(data.get("sma_50")),
        ema_21=_f(data.get("ema_21")),
        ema21_pos=_s("ema21_pos") or None,
        market_status=_s("market_status") or None,
        fear_status=_s("fear_status") or None,
        fear_index=_f(data.get("fear_index")),
        intraday_trend=_s("intraday_trend") or None,
        intraday_momentum=_f(data.get("intraday_momentum")),
        gap_type=_s("gap_type") or None,
        gap_fill_status=_s("gap_fill_status") or None,
        breadth_status=_s("breadth_status") or None,
        sectors_up=int(data["sectors_up"]) if isinstance(data.get("sectors_up"), (int, float)) else None,
        signal_strength=_s("signal_strength") or None,
        signal_reliability=int(data["signal_reliability"]) if isinstance(data.get("signal_reliability"), (int, float)) else None,
        low_3month=_f(data.get("low_3month")),
        distance_3month=_f(data.get("distance_3month")),
        price_diff_3month=_f(data.get("price_diff_3month")),
        eval_3month=_s("eval_3month") or None,
        low_1year=_f(data.get("low_1year")),
        distance_1year=_f(data.get("distance_1year")),
        price_diff_1year=_f(data.get("price_diff_1year")),
        eval_1year=_s("eval_1year") or None,
        signal_strength_deep=_s("signal_strength_deep") or None,
    )
