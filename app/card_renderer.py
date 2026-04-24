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
        "bg_top": (15, 120, 90), "bg_bottom": (8, 70, 55),
        "accent": (120, 255, 180),
        "header_bg": (34, 197, 94), "header_text": (255, 255, 255),
        "header_label": "POT. DİP ALIM SİNYALİ",
        "box_bg": (6, 60, 45),
    },
    "hedef": {
        "bg_top": (10, 110, 85), "bg_bottom": (6, 60, 50),
        "accent": (80, 230, 170),
        "header_bg": (34, 197, 94), "header_text": (255, 255, 255),
        "header_label": "HEDEF OK",
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

    # ---- 3 Kriter Sütunu ----
    has_criteria = any([
        data.gunluk_skor is not None, data.canli_skor is not None, data.giris_skor is not None,
        data.gunluk_kriterler, data.canli_kriterler, data.giris_kriterler,
    ])
    if has_criteria:
        cb_y = sym_y + 110
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
        after_y = sym_y + 110

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

    l1_parts = []
    if data.price is not None:
        up = data.change_pct is not None and data.change_pct >= 0
        arrow = "  ▲" if up else ("  ▼" if data.change_pct is not None else "")
        pct = f"  ({_fmt_pct(data.change_pct)})" if data.change_pct is not None else ""
        l1_parts.append(f"Anlık: {_fmt_price(data.price)}{pct}{arrow}")
    if data.atr_daily is not None:
        l1_parts.append(f"ATR(Gün): {data.atr_daily:.2f}".replace(".", ","))
    if rr_val is not None:
        l1_parts.append(f"R:R  {rr_val:.2f}".replace(".", ","))
    if l1_parts:
        lines.append("      ".join(l1_parts))

    l2_parts = []
    if data.basari_oran is not None:
        bo = f"Başarı: %{data.basari_oran:.1f}".replace(".", ",")
        if data.kazanc is not None and data.kayip is not None:
            bo += f"  ({data.kazanc}K / {data.kayip}L)"
        l2_parts.append(bo)
    if l2_parts:
        lines.append("      ".join(l2_parts))

    y = info_y
    for ln in lines:
        draw.text((pad_x, y), ln, font=ib_font, fill=(255, 255, 255, 230))
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


def render_to_file(data: CardData, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = render_card(data)
    img.save(path, "PNG", optimize=True)
    return path


def build_caption(data: CardData) -> str:
    et = data.event_type.upper()
    sym = data.symbol.upper()
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
