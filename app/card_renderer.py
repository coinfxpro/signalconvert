"""Pillow ile Telegram için görsel kart üretici.

Tasarım referansı: "YENİ SİNYAL" tarzı mavi temalı kart.
Tek bir render() giriş noktası vardır.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .config import settings

# ---------------------------------------------------------------------------
# Kart boyutları ve renk paleti
# ---------------------------------------------------------------------------
CARD_W = 900
CARD_H = 500

# Marka adı — env ile değişebilir
BRAND_NAME = os.getenv("BRAND_NAME", "Algo Trade Hunter")

# Türkiye saati (UTC+3)
TR_TZ = timezone(timedelta(hours=3))

# Renk temaları — event_type -> tema
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
        "header_label": "DİP ALIM SİNYALİ",
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


# ---------------------------------------------------------------------------
# Font yükleme
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
# Logo yükleme (circular crop, RAM'e cache'le)
# ---------------------------------------------------------------------------
_LOGO_CACHE: dict[int, Image.Image] = {}


def _load_logo(size: int) -> Optional[Image.Image]:
    if size in _LOGO_CACHE:
        return _LOGO_CACHE[size]
    # Proje kökündeki logo.png
    base_dir = Path(__file__).resolve().parent.parent
    logo_path = base_dir / "logo.png"
    if not logo_path.exists():
        return None
    try:
        src = Image.open(logo_path).convert("RGBA")
    except Exception:
        return None
    # Logodaki dairesel sembol resmin orta-üst bölgesinde.
    # Merkez-üst bölgeden kare bir alan kırp.
    W, H = src.size
    crop_size = min(W, H) - 80  # biraz iç kısım
    if crop_size <= 0:
        crop_size = min(W, H)
    cx = W // 2
    cy = int(H * 0.42)  # üst-orta
    x0 = max(0, cx - crop_size // 2)
    y0 = max(0, cy - crop_size // 2)
    x1 = min(W, x0 + crop_size)
    y1 = min(H, y0 + crop_size)
    square = src.crop((x0, y0, x1, y1))
    # Daire maskesi
    mask = Image.new("L", square.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, square.size[0], square.size[1]), fill=255)
    square.putalpha(mask)
    logo = square.resize((size, size), Image.LANCZOS)
    _LOGO_CACHE[size] = logo
    return logo


# ---------------------------------------------------------------------------
# Kart verisi
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
    stop: Optional[float] = None
    exit_price: Optional[float] = None
    rr: Optional[float] = None
    confidence: Optional[float] = None
    kar_pct: Optional[float] = None
    duration: Optional[str] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    footer: str = ""  # boşsa BRAND_NAME kullanılır


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


# ---------------------------------------------------------------------------
# Ana render
# ---------------------------------------------------------------------------
def render_card(data: CardData) -> Image.Image:
    theme_key = EVENT_TO_THEME.get(data.event_type.upper(), "signal")
    theme = THEMES[theme_key]
    brand = data.footer or BRAND_NAME

    # Arkaplan gradient
    img = _gradient_bg(CARD_W, CARD_H, theme["bg_top"], theme["bg_bottom"]).convert("RGB")

    # Yuvarlak köşeli kart maskesi
    canvas = Image.new("RGB", (CARD_W, CARD_H), (12, 18, 30))
    mask = Image.new("L", (CARD_W, CARD_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, CARD_W, CARD_H), radius=28, fill=255)
    canvas.paste(img, (0, 0), mask)
    img = canvas.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Sol dikey aksan barı
    draw.rectangle((0, 0, 12, CARD_H), fill=theme["header_bg"])

    # ---- Üst başlık pill ----
    pad_x = 48
    header_y = 36
    header_text = theme["header_label"]
    hb_font = _font(46, bold=True)
    tw = _text_w(draw, header_text, hb_font)
    bbox = draw.textbbox((0, 0), header_text, font=hb_font)
    th = bbox[3] - bbox[1]
    px, py = 22, 14
    rect = (pad_x, header_y, pad_x + tw + px * 2, header_y + th + py * 2)
    _rounded_rect(draw, rect, radius=10, fill=theme["header_bg"])
    draw.text((pad_x + px, header_y + py - 6), header_text,
              font=hb_font, fill=theme["header_text"])

    # Başlık altı çizgi
    line_y = rect[3] + 14
    draw.line((pad_x, line_y, CARD_W - pad_x, line_y),
              fill=(255, 255, 255), width=2)

    # ---- Sağ üst: logo + marka ismi ----
    logo_size = 64
    logo = _load_logo(logo_size)
    brand_font = _font(18, bold=True)
    brand_w = _text_w(draw, brand, brand_font)

    # Sağ kenara yasla
    right_edge = CARD_W - pad_x
    if logo is not None:
        logo_x = right_edge - logo_size
        logo_y = 24
        img.paste(logo, (logo_x, logo_y), logo)
        # Marka metni logonun tam altında, sağa dayalı
        draw.text((right_edge - brand_w, logo_y + logo_size + 4),
                  brand, font=brand_font, fill=(255, 255, 255))
    else:
        draw.text((right_edge - brand_w, 60), brand,
                  font=brand_font, fill=(255, 255, 255))

    # Tarih (sağ üstte, başlık çizgisi altında)
    now_tr = datetime.now(TR_TZ)
    date_str = now_tr.strftime("%d.%m %H:%M")
    df = _font(18, bold=True)
    dw = _text_w(draw, date_str, df)
    draw.text((right_edge - dw, line_y + 10), date_str,
              font=df, fill=(255, 255, 255, 200))

    # ---- Sembol + subtitle / güven ----
    sym_y = line_y + 44
    draw.text((pad_x, sym_y), data.symbol.upper(),
              font=_font(82, bold=True), fill=(255, 255, 255))

    # Sağ tarafa subtitle + güven (iki satır, büyükçe okunur)
    info_font = _font(26, bold=True)
    info_font_s = _font(22, bold=False)
    right_text_x = int(CARD_W * 0.58)
    line1_y = sym_y + 18
    if data.subtitle:
        draw.text((right_text_x, line1_y), data.subtitle,
                  font=info_font, fill=(255, 255, 255))
    if data.confidence is not None:
        conf_txt = f"Güven: %{data.confidence:.1f}".replace(".", ",")
        draw.text((right_text_x, line1_y + 38), conf_txt,
                  font=info_font_s, fill=(255, 255, 255, 220))

    # ---- Alt bilgi kutuları ----
    boxes = []
    if data.entry is not None:
        boxes.append({"label": "GİRİŞ", "value": _fmt_price(data.entry), "color": (255, 255, 255)})
    # ANLIK (fiyat + yanında küçük değişim %)
    if data.price is not None and data.event_type.upper() in ("DIP_AL", "SIGNAL", "PUSU"):
        boxes.append({
            "label": "ANLIK",
            "value": _fmt_price(data.price),
            "color": (120, 255, 180),
            "extra_pct": data.change_pct,
        })
    if data.target is not None:
        boxes.append({"label": "HEDEF", "value": _fmt_price(data.target), "color": (140, 255, 180)})
    if data.stop is not None:
        boxes.append({"label": "STOP", "value": _fmt_price(data.stop), "color": (255, 170, 160)})
    if data.exit_price is not None:
        boxes.append({"label": "ÇIKIŞ", "value": _fmt_price(data.exit_price), "color": (255, 255, 255)})

    # Kâr/zarar varsa K/Z kutusu olarak ekle
    if data.kar_pct is not None and not any(b["label"] == "K/Z" for b in boxes):
        kz_col = (120, 255, 180) if data.kar_pct >= 0 else (255, 140, 140)
        boxes.append({"label": "K/Z", "value": _fmt_pct(data.kar_pct), "color": kz_col})

    if boxes:
        box_y = CARD_H - 170
        total_w = CARD_W - pad_x * 2
        gap = 14
        n = len(boxes)
        box_w = (total_w - gap * (n - 1)) // n
        box_h = 92
        for i, b in enumerate(boxes):
            x0 = pad_x + i * (box_w + gap)
            y0 = box_y
            # Kutu: yarı saydam koyu
            overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            r, g, bl = theme["box_bg"]
            od.rounded_rectangle((0, 0, box_w, box_h), radius=14,
                                 fill=(r, g, bl, 200))
            img.paste(overlay, (x0, y0), overlay)
            draw = ImageDraw.Draw(img)
            # Label
            draw.text((x0 + 16, y0 + 10), b["label"],
                      font=_font(18, bold=True), fill=(255, 255, 255, 200))
            # Value
            value_font = _font(28, bold=True)
            draw.text((x0 + 16, y0 + 36), b["value"],
                      font=value_font, fill=b["color"])
            # Extra değişim yüzdesi (ANLIK kutusunda)
            if "extra_pct" in b and b["extra_pct"] is not None:
                ep = b["extra_pct"]
                ep_color = (120, 255, 180) if ep >= 0 else (255, 160, 160)
                ep_txt = _fmt_pct(ep)
                vw = _text_w(draw, b["value"], value_font)
                draw.text((x0 + 16 + vw + 10, y0 + 44), ep_txt,
                          font=_font(18, bold=True), fill=ep_color)

    # ---- Alt satır: R:R (sol) ve İŞLEM ALINDI rozeti (sağ) ----
    foot_y = CARD_H - 52
    pieces = []
    if data.rr is not None:
        pieces.append(f"R:R  {data.rr:.2f}".replace(".", ","))
    if data.duration:
        pieces.append(f"Süre: {data.duration}")
    foot_text = "   •   ".join(pieces)
    if foot_text:
        draw.text((pad_x, foot_y + 6), foot_text,
                  font=_font(20, bold=True), fill=(255, 255, 255, 220))

    # Sağ alt: durum rozeti
    status_badge = _status_badge_text(data)
    sb_font = _font(20, bold=True)
    if status_badge:
        bw = _text_w(draw, status_badge, sb_font)
        bbox = draw.textbbox((0, 0), status_badge, font=sb_font)
        bh = bbox[3] - bbox[1]
        bx1 = CARD_W - pad_x
        bx0 = bx1 - bw - 28
        by0 = foot_y - 8
        by1 = by0 + bh + 18
        _rounded_rect(draw, (bx0, by0, bx1, by1), radius=10, fill=theme["accent"])
        draw.text((bx0 + 14, by0 + 6), status_badge,
                  font=sb_font, fill=(20, 30, 40))
        # Rozet altına marka ismi
        br_font = _font(16, bold=True)
        brw = _text_w(draw, brand, br_font)
        draw.text((CARD_W - pad_x - brw, by1 + 4), brand,
                  font=br_font, fill=(255, 255, 255, 220))

    return img.convert("RGB")


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
