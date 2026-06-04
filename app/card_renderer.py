"""Pillow ile Telegram için görsel kart üretici.

Zengin layout (v2):
 - Header pill (event rengi) + logo sağ üst
 - Sembol + subtitle + güven
 - 3 sütun kriter paneli (Günlük Dip / Canlı Dip / 15dk Giriş)
 - Fiyat kutuları (GİRİŞ / ANLIK / HEDEF / TP2? / STOP)
 - Alt bilgi satırları (anlık fiyat+değişim, ATR, başarı oranı)
 - Yatırım tavsiyesi değildir uyarısı
 - Sağ alt marka
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageDraw, ImageFont

from .config import settings

# ---------------------------------------------------------------------------
# Boyutlar
# ---------------------------------------------------------------------------
CARD_W = 900
CARD_H = 720

# Varsayılan marka adı (env ile değişir; webhook/test endpointleri bot'tan gelen değerle override eder)
BRAND_NAME = os.getenv("BRAND_NAME", "Alfa Trade Hunter")

TR_TZ = timezone(timedelta(hours=3))

# ---------------------------------------------------------------------------
# Temalar
# ---------------------------------------------------------------------------
THEMES = {
    "signal": {
        "bg_top": (30, 80, 180), "bg_bottom": (20, 50, 130),
        "accent": (255, 210, 60),
        "header_bg": (255, 210, 60), "header_text": (20, 30, 60),
        "header_label": "YENİ SİNYAL",
        "box_bg": (20, 40, 90),
    },
    "dip_al": {
        "bg_top": (30, 80, 180), "bg_bottom": (18, 45, 120),
        "accent": (255, 210, 60),
        "header_bg": (34, 197, 94), "header_text": (255, 255, 255),
        "header_label": "ALIM SİNYALİ",
        "box_bg": (20, 42, 95),
    },
    "hedef": {
        "bg_top": (10, 110, 85), "bg_bottom": (6, 60, 50),
        "accent": (80, 230, 170),
        "header_bg": (34, 197, 94), "header_text": (255, 255, 255),
        "header_label": "Hedef Gerçekleşti",
        "box_bg": (6, 55, 42),
    },
    "stop": {
        "bg_top": (170, 40, 50), "bg_bottom": (110, 25, 35),
        "accent": (255, 220, 120),
        "header_bg": (220, 40, 50), "header_text": (255, 255, 255),
        "header_label": "STOP OLDU",
        "box_bg": (100, 20, 30),
    },
    "trailing": {
        "bg_top": (190, 110, 30), "bg_bottom": (120, 70, 20),
        "accent": (255, 230, 160),
        "header_bg": (245, 158, 11), "header_text": (30, 20, 10),
        "header_label": "TRAILING ÇIKIŞ",
        "box_bg": (110, 65, 18),
    },
    "pusu": {
        "bg_top": (170, 140, 30), "bg_bottom": (110, 90, 20),
        "accent": (255, 245, 160),
        "header_bg": (250, 204, 21), "header_text": (30, 30, 10),
        "header_label": "DİP PUSU",
        "box_bg": (100, 82, 18),
    },
}

EVENT_TO_THEME = {
    "DIP_AL": "dip_al",
    "SIGNAL": "signal",
    "TP1": "hedef",
    "TP2": "hedef",
    "STOP": "stop",
    "TRAILING": "trailing",
    "PUSU": "pusu",
}

# 7 kriter grup başlıkları (kısaltmalar)
GUNLUK_LABELS = ["MA", "Dip", "Mum", "Hcm", "Dön", "Hft", "Ich"]
CANLI_LABELS = ["MA", "Dip", "Mum", "Hcm", "Dön", "Hft", "Ich"]
GIRIS_LABELS = ["Dip", "EMA", "RSI", "MACD", "Hcm", "VWAP", "HL"]

# ---------------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def _find_font(bold: bool = False) -> Optional[str]:
    repo_bold = settings.FONTS_DIR / "Inter-Bold.ttf"
    repo_reg = settings.FONTS_DIR / "Inter-Regular.ttf"
    if bold and repo_bold.exists():
        return str(repo_bold)
    if not bold and repo_reg.exists():
        return str(repo_reg)
    for path in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        is_bold = "bold" in path.lower() or "bd" in path.lower()
        if bold and is_bold:
            return path
        if not bold and not is_bold:
            return path
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _find_font(bold=bold)
    if path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


# ---------------------------------------------------------------------------
# Logo (daire)
# ---------------------------------------------------------------------------
_LOGO_CACHE: dict[int, Image.Image] = {}


def _load_logo(size: int) -> Optional[Image.Image]:
    if size in _LOGO_CACHE:
        return _LOGO_CACHE[size]
    base_dir = Path(__file__).resolve().parent.parent
    logo_path = base_dir / "logo.png"
    if not logo_path.exists():
        return None
    try:
        src = Image.open(logo_path).convert("RGBA")
    except Exception:
        return None
    W, H = src.size
    crop_size = min(W, H) - 80
    if crop_size <= 0:
        crop_size = min(W, H)
    cx = W // 2
    cy = int(H * 0.42)
    x0 = max(0, cx - crop_size // 2)
    y0 = max(0, cy - crop_size // 2)
    x1 = min(W, x0 + crop_size)
    y1 = min(H, y0 + crop_size)
    square = src.crop((x0, y0, x1, y1))
    mask = Image.new("L", square.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, square.size[0], square.size[1]), fill=255)
    square.putalpha(mask)
    logo = square.resize((size, size), Image.LANCZOS)
    _LOGO_CACHE[size] = logo
    return logo


# ---------------------------------------------------------------------------
# CardData
# ---------------------------------------------------------------------------
@dataclass
class CardData:
    event_type: str
    symbol: str
    subtitle: str = ""
    price: Optional[float] = None
    change_pct: Optional[float] = None
    entry: Optional[float] = None
    target: Optional[float] = None
    target2: Optional[float] = None
    stop: Optional[float] = None
    exit_price: Optional[float] = None
    rr: Optional[float] = None
    confidence: Optional[float] = None
    kar_pct: Optional[float] = None
    duration: Optional[str] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    footer: str = ""
    # Zengin veriler
    gunluk_skor: Optional[float] = None
    gunluk_etiket: Optional[str] = None  # "Dün", "Bugün"
    gunluk_kriterler: Optional[str] = None  # "1,0,0,1,1,1,1"
    canli_skor: Optional[float] = None
    canli_kriterler: Optional[str] = None
    giris_skor: Optional[float] = None
    giris_kriterler: Optional[str] = None
    atr_daily: Optional[float] = None
    basari_oran: Optional[float] = None
    kazanc: Optional[int] = None
    kayip: Optional[int] = None
    signal_tag: Optional[str] = None  # "DIP" / "FISH" / "TRANSFORM" — sembol altı büyük rozet
    # AlgoTarama kartı için ek alanlar (Pine'dan gelir)
    periyot: Optional[str] = None
    rsi: Optional[float] = None
    sma_500: Optional[float] = None
    sma_200: Optional[float] = None
    sma_50: Optional[float] = None
    ema_21: Optional[float] = None
    ema21_pos: Optional[str] = None
    market_status: Optional[str] = None
    fear_status: Optional[str] = None
    fear_index: Optional[float] = None
    intraday_trend: Optional[str] = None
    intraday_momentum: Optional[float] = None
    gap_type: Optional[str] = None
    gap_fill_status: Optional[str] = None
    breadth_status: Optional[str] = None
    sectors_up: Optional[int] = None
    signal_strength: Optional[str] = None
    signal_reliability: Optional[int] = None
    low_3month: Optional[float] = None
    distance_3month: Optional[float] = None
    price_diff_3month: Optional[float] = None
    eval_3month: Optional[str] = None
    low_1year: Optional[float] = None
    distance_1year: Optional[float] = None
    price_diff_1year: Optional[float] = None
    eval_1year: Optional[str] = None
    signal_strength_deep: Optional[str] = None


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _gradient_bg(width: int, height: int, color_top, color_bottom) -> Image.Image:
    top = Image.new("RGB", (1, 2), 0)
    top.putpixel((0, 0), color_top)
    top.putpixel((0, 1), color_bottom)
    return top.resize((width, height), Image.BILINEAR)


def _fmt_price(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v: Optional[float], sign: bool = True) -> str:
    if v is None:
        return "—"
    if sign:
        s = "+" if v >= 0 else ""
        return f"%{s}{v:.2f}".replace(".", ",")
    return f"%{v:.2f}".replace(".", ",")


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _parse_criteria(s: Optional[str], expected: int = 7) -> List[bool]:
    """'1,0,0,1,1,1,1' veya '1001111' formatını 7 bool'a çevirir."""
    if not s:
        return [False] * expected
    s = str(s).strip()
    # comma separated
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
    else:
        parts = list(s)
    result = []
    for p in parts[:expected]:
        result.append(p not in ("", "0", "false", "False", "no", "n"))
    while len(result) < expected:
        result.append(False)
    return result


# ---------------------------------------------------------------------------
# Kriter paneli
# ---------------------------------------------------------------------------
def _draw_criteria_box(img: Image.Image, xy, title: str, score_text: str,
                       labels: List[str], flags: List[bool],
                       theme: dict) -> None:
    """Tek bir kriter sütunu çiz (3 sütundan biri)."""
    x0, y0, x1, y1 = xy
    w = x1 - x0
    h = y1 - y0
    # Arka plan
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    r, g, bl = theme["box_bg"]
    od.rounded_rectangle((0, 0, w, h), radius=14, fill=(r, g, bl, 210))
    img.paste(overlay, (x0, y0), overlay)

    draw = ImageDraw.Draw(img)
    # Başlık
    title_font = _font(16, bold=True)
    draw.text((x0 + 14, y0 + 10), title, font=title_font, fill=(255, 255, 255, 220))
    # Skor
    score_font = _font(22, bold=True)
    draw.text((x0 + 14, y0 + 30), score_text, font=score_font, fill=theme["accent"])

    # Kriter listesi — 2 sütun x ~4 satır
    item_font = _font(14, bold=True)
    ok_col = (120, 255, 180)
    no_col = (255, 140, 140)
    label_col = (230, 230, 240)

    # 7 kriteri 2 kolonda dağıt: sol 4, sağ 3 — her biri küçük pill
    col_w = (w - 28) // 2
    col1_x = x0 + 14
    col2_x = x0 + 14 + col_w
    start_y = y0 + 62
    row_h = 22
    pill_h = 18
    for i, (lbl, ok) in enumerate(zip(labels, flags)):
        col = 0 if i < 4 else 1
        row = i if i < 4 else i - 4
        cx = col1_x if col == 0 else col2_x
        cy = start_y + row * row_h
        bg = (30, 90, 60) if ok else (110, 35, 40)
        fg = ok_col if ok else no_col
        # Küçük pill bg
        pw = _text_w(draw, lbl, item_font) + 18
        od2 = ImageDraw.Draw(img, "RGBA")
        od2.rounded_rectangle((cx, cy - 2, cx + pw, cy - 2 + pill_h),
                              radius=5, fill=(bg[0], bg[1], bg[2], 230))
        draw.text((cx + 9, cy), lbl, font=item_font, fill=fg)


# ---------------------------------------------------------------------------
# Ana render
# ---------------------------------------------------------------------------
def render_card(data: CardData) -> Image.Image:
    # AlgoTarama event'i ise farklı bir kart şablonu kullan
    if data.event_type.upper() == "ALGO_TARAMA":
        return render_algo_tarama_card(data)
    theme_key = EVENT_TO_THEME.get(data.event_type.upper(), "signal")
    theme = THEMES[theme_key]
    brand = data.footer or BRAND_NAME

    # Arkaplan gradient + rounded card
    bg = _gradient_bg(CARD_W, CARD_H, theme["bg_top"], theme["bg_bottom"]).convert("RGB")
    canvas = Image.new("RGB", (CARD_W, CARD_H), (12, 18, 30))
    mask = Image.new("L", (CARD_W, CARD_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, CARD_W, CARD_H), radius=28, fill=255)
    canvas.paste(bg, (0, 0), mask)
    img = canvas.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Sol dikey aksan
    draw.rectangle((0, 0, 12, CARD_H), fill=theme["header_bg"])

    pad_x = 40

    # ---- Header pill ----
    header_y = 30
    header_text = theme["header_label"]
    hb_font = _font(42, bold=True)
    tw = _text_w(draw, header_text, hb_font)
    bbox = draw.textbbox((0, 0), header_text, font=hb_font)
    th = bbox[3] - bbox[1]
    px, py = 22, 14
    rect = (pad_x, header_y, pad_x + tw + px * 2, header_y + th + py * 2)
    _rounded_rect(draw, rect, radius=10, fill=theme["header_bg"])
    draw.text((pad_x + px, header_y + py - 6), header_text,
              font=hb_font, fill=theme["header_text"])

    line_y = rect[3] + 12
    draw.line((pad_x, line_y, CARD_W - pad_x, line_y),
              fill=(255, 255, 255), width=2)

    # ---- Sağ üst: logo + marka ----
    logo_size = 60
    logo = _load_logo(logo_size)
    brand_font = _font(16, bold=True)
    brand_w = _text_w(draw, brand, brand_font)
    right_edge = CARD_W - pad_x
    if logo is not None:
        logo_x = right_edge - logo_size
        logo_y = 22
        img.paste(logo, (logo_x, logo_y), logo)
        draw.text((right_edge - brand_w, logo_y + logo_size + 2),
                  brand, font=brand_font, fill=(255, 255, 255))

    # Tarih
    now_tr = datetime.now(TR_TZ)
    date_str = now_tr.strftime("%d.%m %H:%M")
    df = _font(16, bold=True)
    dw = _text_w(draw, date_str, df)
    draw.text((right_edge - dw, line_y + 10), date_str,
              font=df, fill=(255, 255, 255, 210))

    # ---- Sembol + subtitle/güven ----
    sym_y = line_y + 38
    draw.text((pad_x, sym_y), data.symbol.upper(),
              font=_font(70, bold=True), fill=(255, 255, 255))

    info_font = _font(24, bold=True)
    info_font_s = _font(20, bold=False)
    right_text_x = int(CARD_W * 0.58)
    if data.subtitle:
        draw.text((right_text_x, sym_y + 14), data.subtitle,
                  font=info_font, fill=(255, 255, 255))
    if data.confidence is not None:
        conf_txt = f"Güven: %{data.confidence:.1f}".replace(".", ",")
        draw.text((right_text_x, sym_y + 48), conf_txt,
                  font=info_font_s, fill=(255, 255, 255, 220))

    # ---- Sinyal tipi rozeti (sembol altı) ----
    tag_extra_y = 0
    if data.signal_tag:
        tag = data.signal_tag.strip().upper()
        TAG_COLORS = {
            "DIP":       ((34, 197, 94),  (255, 255, 255)),   # yeşil
            "FISH":      ((59, 130, 246), (255, 255, 255)),   # mavi
            "TRANSFORM": ((168, 85, 247), (255, 255, 255)),   # mor
        }
        bg_col, fg_col = TAG_COLORS.get(tag, ((100, 116, 139), (255, 255, 255)))
        tag_font = _font(32, bold=True)
        tw_tag = _text_w(draw, tag, tag_font)
        bbox_tag = draw.textbbox((0, 0), tag, font=tag_font)
        th_tag = bbox_tag[3] - bbox_tag[1]
        px_t, py_t = 18, 8
        tag_y = sym_y + 92
        tag_rect = (pad_x, tag_y, pad_x + tw_tag + px_t * 2, tag_y + th_tag + py_t * 2)
        _rounded_rect(draw, tag_rect, radius=10, fill=bg_col)
        draw.text((pad_x + px_t, tag_y + py_t - 4), tag,
                  font=tag_font, fill=fg_col)
        tag_extra_y = (th_tag + py_t * 2) + 12

    # ---- 3 Kriter Sütunu ----
    has_criteria = any([
        data.gunluk_skor is not None, data.canli_skor is not None, data.giris_skor is not None,
        data.gunluk_kriterler, data.canli_kriterler, data.giris_kriterler,
    ])
    if has_criteria:
        cb_y = sym_y + 110 + tag_extra_y
        cb_h = 160
        total_w = CARD_W - pad_x * 2
        gap = 14
        col_w = (total_w - gap * 2) // 3
        cols = [
            ("GÜNLÜK DİP",
             f"{_fmt_skor(data.gunluk_skor)}/7" + (f"  ({data.gunluk_etiket})" if data.gunluk_etiket else ""),
             GUNLUK_LABELS, _parse_criteria(data.gunluk_kriterler)),
            ("CANLI DİP",
             f"{_fmt_skor(data.canli_skor)}/7",
             CANLI_LABELS, _parse_criteria(data.canli_kriterler)),
            ("15dk GİRİŞ",
             f"{_fmt_skor(data.giris_skor)}/7",
             GIRIS_LABELS, _parse_criteria(data.giris_kriterler)),
        ]
        for i, (title, score_text, labels, flags) in enumerate(cols):
            x0 = pad_x + i * (col_w + gap)
            _draw_criteria_box(img, (x0, cb_y, x0 + col_w, cb_y + cb_h),
                               title, score_text, labels, flags, theme)
        after_y = cb_y + cb_h + 14
    else:
        after_y = sym_y + 110 + tag_extra_y

    draw = ImageDraw.Draw(img)

    # ---- Fiyat kutuları ----
    def _rel_pct(v: Optional[float]) -> Optional[float]:
        """Giriş fiyatına göre relatif % (target/stop için)."""
        if v is None or data.entry is None or data.entry == 0:
            return None
        return (v - data.entry) / data.entry * 100

    boxes = []
    if data.entry is not None:
        boxes.append({"label": "GİRİŞ", "value": _fmt_price(data.entry), "color": (255, 255, 255)})
    if data.price is not None and data.event_type.upper() in ("DIP_AL", "SIGNAL", "PUSU"):
        boxes.append({
            "label": "ANLIK", "value": _fmt_price(data.price),
            "color": (120, 255, 180), "extra_pct": data.change_pct,
        })
    if data.target is not None:
        boxes.append({"label": "HEDEF 1" if data.target2 else "HEDEF",
                      "value": _fmt_price(data.target), "color": (140, 255, 180),
                      "extra_pct": _rel_pct(data.target)})
    if data.target2 is not None:
        boxes.append({"label": "HEDEF 2", "value": _fmt_price(data.target2),
                      "color": (140, 255, 180), "extra_pct": _rel_pct(data.target2)})
    if data.stop is not None:
        boxes.append({"label": "STOP", "value": _fmt_price(data.stop),
                      "color": (255, 170, 160), "extra_pct": _rel_pct(data.stop)})
    if data.exit_price is not None:
        boxes.append({"label": "ÇIKIŞ", "value": _fmt_price(data.exit_price), "color": (255, 255, 255)})
    if data.kar_pct is not None and not any(b["label"] == "K/Z" for b in boxes):
        kz_col = (120, 255, 180) if data.kar_pct >= 0 else (255, 140, 140)
        boxes.append({"label": "K/Z", "value": _fmt_pct(data.kar_pct), "color": kz_col})

    if boxes:
        box_y = after_y
        total_w = CARD_W - pad_x * 2
        gap = 10
        n = len(boxes)
        box_w = (total_w - gap * (n - 1)) // n
        box_h = 78
        for i, b in enumerate(boxes):
            x0 = pad_x + i * (box_w + gap)
            overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            r, g, bl = theme["box_bg"]
            od.rounded_rectangle((0, 0, box_w, box_h), radius=12, fill=(r, g, bl, 200))
            img.paste(overlay, (x0, box_y), overlay)
            draw = ImageDraw.Draw(img)
            draw.text((x0 + 12, box_y + 8), b["label"],
                      font=_font(14, bold=True), fill=(255, 255, 255, 200))
            value_font = _font(24, bold=True)
            draw.text((x0 + 12, box_y + 32), b["value"],
                      font=value_font, fill=b["color"])
            if "extra_pct" in b and b["extra_pct"] is not None:
                ep = b["extra_pct"]
                ep_color = (120, 255, 180) if ep >= 0 else (255, 160, 160)
                draw.text((x0 + 12, box_y + 60), _fmt_pct(ep),
                          font=_font(14, bold=True), fill=ep_color)
        info_y = box_y + box_h + 14
    else:
        info_y = after_y

    # ---- Alt bilgi satırları ----
    draw = ImageDraw.Draw(img)
    ib_font = _font(17, bold=True)
    lines: List[str] = []

    # R:R — Pine göndermediyse entry/target/stop'tan hesapla
    rr_val = data.rr
    if rr_val is None and data.entry is not None and data.target is not None and data.stop is not None:
        risk = data.entry - data.stop
        if risk > 0:
            rr_val = (data.target - data.entry) / risk

    DEFAULT_FILL = (255, 255, 255, 230)
    rendered: list = []  # list of (text, fill)

    l1_parts = []
    if data.price is not None:
        up = data.change_pct is not None and data.change_pct >= 0
        arrow = "  ▲" if up else ("  ▼" if data.change_pct is not None else "")
        pct = f"  ({_fmt_pct(data.change_pct)})" if data.change_pct is not None else ""
        l1_parts.append(f"Anlık: {_fmt_price(data.price)}{pct}{arrow}")
    if data.atr_daily is not None:
        l1_parts.append(f"ATR(Gün): {data.atr_daily:.2f}".replace(".", ","))
    if rr_val is not None:
        l1_parts.append(f"R:R  {rr_val:.2f} (Risk Ödül Oranı)".replace(".", ","))
    if l1_parts:
        rendered.append(("      ".join(l1_parts), DEFAULT_FILL))

    # TP1 olayında: stop'un break-even'a çekildiğini bildir
    if data.event_type.upper() == "TP1" and data.entry is not None:
        rendered.append(
            (f"Stop → Giriş seviyesine çekildi  ({_fmt_price(data.entry)} — Break-Even)",
             DEFAULT_FILL))

    if data.basari_oran is not None:
        bo = f"Başarı: %{data.basari_oran:.1f}".replace(".", ",")
        if data.kazanc is not None and data.kayip is not None:
            bo += f"  ({data.kazanc}K / {data.kayip}L)"
        # Renk: <50 kırmızı, 50-70 turuncu, >=70 yeşil
        if data.basari_oran >= 70:
            bo_fill = (120, 255, 170, 240)
        elif data.basari_oran >= 50:
            bo_fill = (255, 180, 80, 240)
        else:
            bo_fill = (255, 110, 110, 240)
        rendered.append((bo, bo_fill))

    y = info_y
    for txt, fill in rendered:
        draw.text((pad_x, y), txt, font=ib_font, fill=fill)
        y += 26

    # ---- Ayırıcı + uyarı (2 satır) ----
    warning_y = CARD_H - 88
    draw.line((pad_x, warning_y, CARD_W - pad_x, warning_y),
              fill=(255, 255, 255, 40), width=1)
    warn_font = _font(14, bold=True)
    draw.text((pad_x, warning_y + 10),
              "!  Bu sinyal yatırım tavsiyesi değildir.",
              font=warn_font, fill=(255, 230, 160, 230))
    draw.text((pad_x, warning_y + 30),
              "   Potansiyel hesaplamalara dayanmaktadır.",
              font=warn_font, fill=(255, 230, 160, 200))

    # Sağ alt: durum rozeti + marka
    status_badge = _status_badge_text(data)
    if status_badge:
        sb_font = _font(17, bold=True)
        bw = _text_w(draw, status_badge, sb_font)
        bbox = draw.textbbox((0, 0), status_badge, font=sb_font)
        bh = bbox[3] - bbox[1]
        bx1 = CARD_W - pad_x
        bx0 = bx1 - bw - 24
        by0 = warning_y + 8
        by1 = by0 + bh + 14
        _rounded_rect(draw, (bx0, by0, bx1, by1), radius=8, fill=theme["accent"])
        draw.text((bx0 + 12, by0 + 4), status_badge,
                  font=sb_font, fill=(20, 30, 40))
        # rozet altına marka
        br_font = _font(14, bold=True)
        brw = _text_w(draw, brand, br_font)
        draw.text((CARD_W - pad_x - brw, by1 + 4), brand,
                  font=br_font, fill=(255, 255, 255, 220))

    return img.convert("RGB")


def _fmt_skor(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _status_badge_text(data: CardData) -> str:
    et = data.event_type.upper()
    mapping = {
        "DIP_AL": "İŞLEM ALINDI",
        "SIGNAL": "İŞLEM ALINDI",
        "TP1": "HEDEF 1 OK",
        "TP2": "HEDEF 2 OK",
        "STOP": "STOP",
        "TRAILING": "TRAIL ÇIKIŞ",
        "PUSU": "KOŞUL HAZIR",
    }
    return mapping.get(et, "")


# ---------------------------------------------------------------------------
# AlgoTarama kart şablonu (BIST Genel + Dip Analizi + Teknik Özet)
# ---------------------------------------------------------------------------
ALGO_CARD_W = 900
ALGO_CARD_H = 1200

ALGO_THEME = {
    "bg_top": (20, 35, 75),
    "bg_bottom": (12, 22, 50),
    "accent": (255, 210, 60),
    "header_bg": (34, 197, 94),
    "header_text": (255, 255, 255),
    "header_label": "ALGO TARAMA",
    "box_bg": (16, 30, 65),
    "section_bg": (18, 34, 72),
}

TAG_COLORS = {
    "DIP":       ((34, 197, 94),  (255, 255, 255)),
    "FISH":      ((59, 130, 246), (255, 255, 255)),
    "TRANSFORM": ((168, 85, 247), (255, 255, 255)),
}


def _dot(draw: ImageDraw.ImageDraw, xy, color, r: int = 6) -> None:
    x, y = xy
    draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _trend_color(positive: bool) -> tuple:
    return (120, 255, 180) if positive else (255, 140, 140)


def _draw_section_box(img: Image.Image, xy, theme: dict, alpha: int = 200) -> None:
    x0, y0, x1, y1 = xy
    overlay = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    r, g, b = theme["section_bg"]
    od.rounded_rectangle((0, 0, x1 - x0, y1 - y0), radius=14, fill=(r, g, b, alpha))
    img.paste(overlay, (x0, y0), overlay)


def render_algo_tarama_card(data: CardData) -> Image.Image:
    theme = ALGO_THEME
    brand = data.footer or BRAND_NAME
    W, H = ALGO_CARD_W, ALGO_CARD_H

    bg = _gradient_bg(W, H, theme["bg_top"], theme["bg_bottom"]).convert("RGB")
    canvas = Image.new("RGB", (W, H), (12, 18, 30))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W, H), radius=28, fill=255)
    canvas.paste(bg, (0, 0), mask)
    img = canvas.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Sol dikey aksan
    draw.rectangle((0, 0, 12, H), fill=theme["header_bg"])
    pad_x = 40

    # ---- Header ----
    header_y = 30
    header_text = theme["header_label"]
    hb_font = _font(38, bold=True)
    tw = _text_w(draw, header_text, hb_font)
    bbox = draw.textbbox((0, 0), header_text, font=hb_font)
    th = bbox[3] - bbox[1]
    px, py = 22, 14
    rect = (pad_x, header_y, pad_x + tw + px * 2, header_y + th + py * 2)
    _rounded_rect(draw, rect, radius=10, fill=theme["header_bg"])
    draw.text((pad_x + px, header_y + py - 6), header_text,
              font=hb_font, fill=theme["header_text"])
    line_y = rect[3] + 12
    draw.line((pad_x, line_y, W - pad_x, line_y), fill=(255, 255, 255), width=2)

    # ---- Sağ üst: logo + marka + tarih ----
    logo_size = 56
    logo = _load_logo(logo_size)
    brand_font = _font(15, bold=True)
    brand_w = _text_w(draw, brand, brand_font)
    right_edge = W - pad_x
    if logo is not None:
        logo_x = right_edge - logo_size
        logo_y = 22
        img.paste(logo, (logo_x, logo_y), logo)
        draw.text((right_edge - brand_w, logo_y + logo_size + 2),
                  brand, font=brand_font, fill=(255, 255, 255))

    now_tr = datetime.now(TR_TZ)
    date_str = now_tr.strftime("%d.%m %H:%M")
    df = _font(15, bold=True)
    dw = _text_w(draw, date_str, df)
    draw.text((right_edge - dw, line_y + 10), date_str,
              font=df, fill=(255, 255, 255, 210))

    # ---- Sembol ----
    sym_y = line_y + 38
    draw.text((pad_x, sym_y), data.symbol.upper(),
              font=_font(64, bold=True), fill=(255, 255, 255))

    # Periyot + fiyat (sağda)
    info_font = _font(20, bold=True)
    info_lines = []
    if data.periyot:
        info_lines.append(f"PERİYOT: {data.periyot}")
    if data.price is not None:
        info_lines.append(f"FİYAT: {data.price:.2f}".replace(".", ","))
    iy = sym_y + 10
    for ln in info_lines:
        lw = _text_w(draw, ln, info_font)
        draw.text((right_edge - lw, iy), ln, font=info_font, fill=(255, 255, 255, 230))
        iy += 28

    # Subtitle
    if data.subtitle:
        draw.text((pad_x, sym_y + 78), data.subtitle,
                  font=_font(20, bold=True), fill=(255, 230, 160))

    # ---- Sinyal Tag Rozeti ----
    cur_y = sym_y + 110
    if data.signal_tag:
        tag = data.signal_tag.strip().upper()
        bg_col, fg_col = TAG_COLORS.get(tag, ((100, 116, 139), (255, 255, 255)))
        tag_font = _font(28, bold=True)
        tw_tag = _text_w(draw, tag, tag_font)
        bbox_tag = draw.textbbox((0, 0), tag, font=tag_font)
        th_tag = bbox_tag[3] - bbox_tag[1]
        px_t, py_t = 16, 6
        tag_rect = (pad_x, cur_y, pad_x + tw_tag + px_t * 2, cur_y + th_tag + py_t * 2)
        _rounded_rect(draw, tag_rect, radius=10, fill=bg_col)
        draw.text((pad_x + px_t, cur_y + py_t - 4), tag,
                  font=tag_font, fill=fg_col)
        cur_y += th_tag + py_t * 2 + 16
    else:
        cur_y += 8

    # ---- Günlük Teknik Özet ----
    sec_h = 220
    _draw_section_box(img, (pad_x, cur_y, W - pad_x, cur_y + sec_h), theme)
    draw = ImageDraw.Draw(img)
    title_font = _font(18, bold=True)
    draw.text((pad_x + 16, cur_y + 12), "📈 GÜNLÜK TEKNİK ÖZET",
              font=title_font, fill=(255, 210, 60))

    row_font = _font(16, bold=True)
    rows = []
    if data.change_pct is not None:
        rows.append(("Günlük Değişim", _fmt_pct(data.change_pct), data.change_pct >= 0))
    if data.sma_500 is not None and data.price is not None:
        rows.append(("Günlük 500SMA", f"{data.sma_500:.2f}".replace(".", ","), data.price > data.sma_500))
    if data.sma_200 is not None and data.price is not None:
        rows.append(("Günlük 200SMA", f"{data.sma_200:.2f}".replace(".", ","), data.price > data.sma_200))
    if data.sma_50 is not None and data.price is not None:
        rows.append(("Günlük 50SMA", f"{data.sma_50:.2f}".replace(".", ","), data.price > data.sma_50))
    if data.ema_21 is not None and data.price is not None:
        rows.append(("Günlük EMA21", f"{data.ema_21:.2f}".replace(".", ","), data.price > data.ema_21))
    if data.rsi is not None:
        rsi_good = 30 <= data.rsi <= 70
        rows.append(("RSI", f"{data.rsi:.2f}".replace(".", ","), rsi_good))

    ry = cur_y + 44
    for label, value, positive in rows[:6]:
        draw.text((pad_x + 16, ry), label, font=row_font, fill=(220, 230, 240))
        _dot(draw, (W - pad_x - 28, ry + 10), _trend_color(positive), 5)
        vw = _text_w(draw, value, row_font)
        draw.text((W - pad_x - 48 - vw, ry), value, font=row_font, fill=_trend_color(positive))
        ry += 26
    cur_y += sec_h + 14

    # ---- BIST Genel Görünüm ----
    sec_h = 220
    _draw_section_box(img, (pad_x, cur_y, W - pad_x, cur_y + sec_h), theme)
    draw = ImageDraw.Draw(img)
    draw.text((pad_x + 16, cur_y + 12), "📊 BIST GENEL GÖRÜNÜM",
              font=title_font, fill=(255, 210, 60))

    bist_rows = []
    if data.market_status:
        bist_rows.append(("Durum", data.market_status))
    if data.fear_status is not None:
        fi = f" ({data.fear_index:.2f})".replace(".", ",") if data.fear_index is not None else ""
        bist_rows.append(("Fear Index", f"{data.fear_status}{fi}"))
    if data.intraday_trend:
        im = f" (%{data.intraday_momentum:.2f})".replace(".", ",") if data.intraday_momentum is not None else ""
        bist_rows.append(("Gün İçi Trend", f"{data.intraday_trend}{im}"))
    if data.gap_type:
        gf = f" - {data.gap_fill_status}" if data.gap_fill_status else ""
        bist_rows.append(("Gap", f"{data.gap_type}{gf}"))
    if data.breadth_status:
        su = f" ({data.sectors_up}/4)" if data.sectors_up is not None else ""
        bist_rows.append(("Sektör Durumu", f"{data.breadth_status}{su}"))
    if data.signal_strength:
        sr = f" ⭐{data.signal_reliability}" if data.signal_reliability is not None else ""
        bist_rows.append(("Sinyal Kalitesi", f"{data.signal_strength}{sr}"))

    ry = cur_y + 44
    for label, value in bist_rows[:6]:
        draw.text((pad_x + 16, ry), f"├ {label}:", font=row_font, fill=(220, 230, 240))
        draw.text((pad_x + 200, ry), value, font=row_font, fill=(255, 255, 255))
        ry += 26
    cur_y += sec_h + 14

    # ---- Dip Analizi ----
    sec_h = 240
    _draw_section_box(img, (pad_x, cur_y, W - pad_x, cur_y + sec_h), theme)
    draw = ImageDraw.Draw(img)
    draw.text((pad_x + 16, cur_y + 12), "🎯 DİP ANALİZİ",
              font=title_font, fill=(255, 210, 60))

    col_w = (W - pad_x * 2 - 30) // 2

    # 3 Aylık
    bx0 = pad_x + 16
    by = cur_y + 44
    draw.text((bx0, by), "3 AYLIK", font=_font(16, bold=True), fill=(255, 210, 60))
    by += 22
    if data.low_3month is not None:
        draw.text((bx0, by), f"Dip: {data.low_3month:.2f} TL".replace(".", ","),
                  font=row_font, fill=(255, 255, 255)); by += 22
    if data.price_diff_3month is not None:
        draw.text((bx0, by), f"Fark: {data.price_diff_3month:.2f} TL".replace(".", ","),
                  font=row_font, fill=(220, 230, 240)); by += 22
    if data.distance_3month is not None:
        ev = f" {data.eval_3month}" if data.eval_3month else ""
        draw.text((bx0, by), f"Uzaklık: %{data.distance_3month:.2f}{ev}".replace(".", ","),
                  font=row_font, fill=(255, 255, 255)); by += 22

    # Yıllık
    bx1 = pad_x + 16 + col_w + 30
    by = cur_y + 44
    draw.text((bx1, by), "YILLIK", font=_font(16, bold=True), fill=(255, 210, 60))
    by += 22
    if data.low_1year is not None:
        draw.text((bx1, by), f"Dip: {data.low_1year:.2f} TL".replace(".", ","),
                  font=row_font, fill=(255, 255, 255)); by += 22
    if data.price_diff_1year is not None:
        draw.text((bx1, by), f"Fark: {data.price_diff_1year:.2f} TL".replace(".", ","),
                  font=row_font, fill=(220, 230, 240)); by += 22
    if data.distance_1year is not None:
        ev = f" {data.eval_1year}" if data.eval_1year else ""
        draw.text((bx1, by), f"Uzaklık: %{data.distance_1year:.2f}{ev}".replace(".", ","),
                  font=row_font, fill=(255, 255, 255)); by += 22

    # Genel değerlendirme
    if data.signal_strength_deep:
        deep_y = cur_y + sec_h - 50
        draw.line((pad_x + 16, deep_y - 8, W - pad_x - 16, deep_y - 8),
                  fill=(255, 255, 255, 40), width=1)
        draw.text((pad_x + 16, deep_y),
                  f"Değerlendirme: {data.signal_strength_deep}",
                  font=_font(18, bold=True), fill=(255, 210, 60))

    cur_y += sec_h + 14

    # ---- Uyarı + Marka ----
    warn_y = H - 70
    draw.line((pad_x, warn_y, W - pad_x, warn_y), fill=(255, 255, 255, 40), width=1)
    warn_font = _font(13, bold=True)
    draw.text((pad_x, warn_y + 10),
              "!  Bu sinyal yatırım tavsiyesi değildir. Potansiyel hesaplamalara dayanmaktadır.",
              font=warn_font, fill=(255, 230, 160, 220))
    br_font = _font(13, bold=True)
    brw = _text_w(draw, brand, br_font)
    draw.text((W - pad_x - brw, warn_y + 32), brand,
              font=br_font, fill=(255, 255, 255, 220))

    return img.convert("RGB")


def render_to_file(data: CardData, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = render_card(data)
    img.save(path, "PNG", optimize=True)
    return path


def build_caption(data: CardData) -> str:
    et = data.event_type.upper()
    sym = data.symbol.upper()
    if et == "ALGO_TARAMA":
        tag = (data.signal_tag or "").upper()
        emoji = {"DIP": "🟢", "FISH": "🔵", "TRANSFORM": "🟣"}.get(tag, "🟢")
        return f"{emoji} <b>{sym}</b> | {data.subtitle or 'Algo Tarama'}"
    if et in ("DIP_AL", "SIGNAL"):
        return f"🟢 <b>{sym}</b> | {data.subtitle or 'Yeni Sinyal'}"
    if et == "TP1":
        return f"🟡 <b>{sym}</b> | HEDEF 1 OK | Kâr: {_fmt_pct(data.kar_pct)}"
    if et == "TP2":
        return f"🟢 <b>{sym}</b> | HEDEF 2 OK | Kâr: {_fmt_pct(data.kar_pct)}"
    if et == "STOP":
        return f"🔴 <b>{sym}</b> | STOP | K/Z: {_fmt_pct(data.kar_pct)}"
    if et == "TRAILING":
        return f"🟠 <b>{sym}</b> | TRAIL ÇIKIŞ | Kâr: {_fmt_pct(data.kar_pct)}"
    if et == "PUSU":
        return f"🟡 <b>{sym}</b> | Dip Pusu"
    return f"<b>{sym}</b> | {et}"
