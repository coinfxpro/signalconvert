"""Pillow ile Telegram için görsel kart üretici.

Tasarım: TransformML projesindeki 'YENİ SİNYAL' / 'HEDEF OK' / 'STOP OLDU'
kartlarından ilham almıştır. Tek bir render() giriş noktası vardır.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import settings

# ---------------------------------------------------------------------------
# Kart boyutları ve renk paleti
# ---------------------------------------------------------------------------
CARD_W = 900
CARD_H = 500

# Renk temaları — event_type -> (bg_top, bg_bottom, accent, header_text_bg)
THEMES = {
    "signal": {  # Mavi tonlu YENİ SİNYAL
        "bg_top": (30, 80, 180),
        "bg_bottom": (20, 50, 130),
        "accent": (255, 210, 60),
        "header_bg": (255, 210, 60),
        "header_text": (20, 30, 60),
        "header_label": "YENİ SİNYAL",
    },
    "dip_al": {  # Yeşil tonlu DİP ALIM
        "bg_top": (15, 120, 90),
        "bg_bottom": (8, 70, 55),
        "accent": (120, 255, 180),
        "header_bg": (34, 197, 94),
        "header_text": (255, 255, 255),
        "header_label": "DİP ALIM SİNYALİ",
    },
    "hedef": {  # Koyu yeşil HEDEF OK
        "bg_top": (10, 110, 85),
        "bg_bottom": (6, 60, 50),
        "accent": (80, 230, 170),
        "header_bg": (34, 197, 94),
        "header_text": (255, 255, 255),
        "header_label": "HEDEF OK",
    },
    "stop": {  # Kırmızı STOP OLDU
        "bg_top": (170, 40, 50),
        "bg_bottom": (110, 25, 35),
        "accent": (255, 220, 120),
        "header_bg": (220, 40, 50),
        "header_text": (255, 255, 255),
        "header_label": "STOP OLDU",
    },
    "trailing": {  # Turuncu TRAILING
        "bg_top": (190, 110, 30),
        "bg_bottom": (120, 70, 20),
        "accent": (255, 230, 160),
        "header_bg": (245, 158, 11),
        "header_text": (30, 20, 10),
        "header_label": "TRAILING ÇIKIŞ",
    },
    "pusu": {  # Sarı PUSU
        "bg_top": (170, 140, 30),
        "bg_bottom": (110, 90, 20),
        "accent": (255, 245, 160),
        "header_bg": (250, 204, 21),
        "header_text": (30, 30, 10),
        "header_label": "DİP PUSU",
    },
}

# Event type -> tema eşlemesi
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
# Font yükleme — Docker image'a fonts-dejavu kuracağız, Windows'ta Arial'e düşer
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def _find_font(bold: bool = False) -> Optional[str]:
    # Repo içi özel font varsa öncelikle onu kullan
    repo_bold = settings.FONTS_DIR / "Inter-Bold.ttf"
    repo_reg = settings.FONTS_DIR / "Inter-Regular.ttf"
    if bold and repo_bold.exists():
        return str(repo_bold)
    if not bold and repo_reg.exists():
        return str(repo_reg)

    for path in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        if bold and "bold" not in path.lower() and "bd" not in path.lower():
            continue
        if not bold and ("bold" in path.lower() or "bd" in path.lower()):
            continue
        return path
    # Son çare: herhangi bir aday
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
# Kart verisi
# ---------------------------------------------------------------------------
@dataclass
class CardData:
    event_type: str                 # DIP_AL, TP1, STOP vb.
    symbol: str
    subtitle: str = ""              # örn. "15M %3 Kâr Al"
    price: Optional[float] = None   # Anlık fiyat
    change_pct: Optional[float] = None
    entry: Optional[float] = None
    target: Optional[float] = None  # TP1 veya TP2
    stop: Optional[float] = None
    exit_price: Optional[float] = None
    rr: Optional[float] = None
    confidence: Optional[float] = None
    kar_pct: Optional[float] = None   # Kâr/Zarar yüzdesi
    duration: Optional[str] = None    # Süre metni
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    footer: str = "SignalConvert"


# ---------------------------------------------------------------------------
# Çizim yardımcıları
# ---------------------------------------------------------------------------
def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _gradient_bg(width: int, height: int, color_top, color_bottom) -> Image.Image:
    base = Image.new("RGB", (width, height), color_top)
    top = Image.new("RGB", (1, 2), 0)
    top.putpixel((0, 0), color_top)
    top.putpixel((0, 1), color_bottom)
    grad = top.resize((width, height), Image.BILINEAR)
    return grad


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


# ---------------------------------------------------------------------------
# Ana render
# ---------------------------------------------------------------------------
def render_card(data: CardData) -> Image.Image:
    theme_key = EVENT_TO_THEME.get(data.event_type.upper(), "signal")
    theme = THEMES[theme_key]

    # Arkaplan gradient
    img = _gradient_bg(CARD_W, CARD_H, theme["bg_top"], theme["bg_bottom"])
    img = img.convert("RGB")

    # Dış kart (yuvarlak köşeli maske)
    canvas = Image.new("RGB", (CARD_W, CARD_H), (12, 18, 30))
    mask = Image.new("L", (CARD_W, CARD_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, CARD_W, CARD_H), radius=28, fill=255)
    canvas.paste(img, (0, 0), mask)
    img = canvas

    draw = ImageDraw.Draw(img)

    # Sol üst renkli bar (dikey aksan)
    draw.rectangle((0, 0, 12, CARD_H), fill=theme["header_bg"])

    # Üst başlık bloğu
    header_pad_x = 48
    header_y = 36
    header_text = theme["header_label"]
    hb_font = _font(46, bold=True)
    bbox = draw.textbbox((0, 0), header_text, font=hb_font)
    hw = bbox[2] - bbox[0]
    hh = bbox[3] - bbox[1]
    # Renkli etiket arka planı
    pad_x, pad_y = 22, 14
    rect = (header_pad_x, header_y, header_pad_x + hw + pad_x * 2, header_y + hh + pad_y * 2)
    _rounded_rect(draw, rect, radius=10, fill=theme["header_bg"])
    draw.text((header_pad_x + pad_x, header_y + pad_y - 4), header_text,
              font=hb_font, fill=theme["header_text"])

    # Başlık altı ince çizgi
    line_y = rect[3] + 14
    draw.line((header_pad_x, line_y, CARD_W - header_pad_x, line_y),
              fill=(255, 255, 255, 60), width=2)

    # Sağ üst: logo dairesi + marka
    logo_r = 34
    cx, cy = CARD_W - 80, 70
    draw.ellipse((cx - logo_r, cy - logo_r, cx + logo_r, cy + logo_r),
                 outline=(255, 255, 255), width=3)
    lf = _font(28, bold=True)
    draw.text((cx - 10, cy - 18), "S", font=lf, fill=(255, 255, 255))
    draw.text((CARD_W - 180, cy + logo_r + 4), data.footer,
              font=_font(16, bold=True), fill=(255, 255, 255, 200))

    # ---- SEMBOL (büyük) ----
    sym_y = line_y + 24
    draw.text((header_pad_x, sym_y), data.symbol.upper(),
              font=_font(86, bold=True), fill=(255, 255, 255))

    # Subtitle (örn. "15M %3 Kâr Al")
    if data.subtitle:
        draw.text((header_pad_x, sym_y + 96), data.subtitle,
                  font=_font(22, bold=True), fill=(255, 255, 255, 200))
        if data.confidence is not None:
            draw.text((header_pad_x, sym_y + 124),
                      f"Güven: %{data.confidence:.1f}".replace(".", ","),
                      font=_font(20, bold=False), fill=(255, 255, 255, 180))

    # Sağ büyük yüzde — kâr/zarar veya değişim
    big_pct = data.kar_pct if data.kar_pct is not None else data.change_pct
    if big_pct is not None:
        pct_text = _fmt_pct(big_pct)
        pf = _font(78, bold=True)
        bbox = draw.textbbox((0, 0), pct_text, font=pf)
        pw = bbox[2] - bbox[0]
        draw.text((CARD_W - header_pad_x - pw, sym_y + 10),
                  pct_text, font=pf, fill=theme["accent"])
        # Alt etiket
        lbl = "Kâr" if data.kar_pct is not None else "Değişim"
        lbl_font = _font(22, bold=True)
        bbox = draw.textbbox((0, 0), lbl, font=lbl_font)
        lw = bbox[2] - bbox[0]
        draw.text((CARD_W - header_pad_x - lw, sym_y + 96),
                  lbl, font=lbl_font, fill=(255, 255, 255, 220))

    # ---- Bilgi kutuları (GİRİŞ / HEDEF / STOP / ÇIKIŞ) ----
    boxes = []
    if data.entry is not None:
        boxes.append(("GİRİŞ", _fmt_price(data.entry), (255, 255, 255)))
    if data.target is not None:
        boxes.append(("HEDEF", _fmt_price(data.target), (140, 255, 180)))
    if data.stop is not None:
        boxes.append(("STOP", _fmt_price(data.stop), (255, 170, 160)))
    if data.exit_price is not None:
        boxes.append(("ÇIKIŞ", _fmt_price(data.exit_price), (255, 255, 255)))
    elif data.price is not None and data.exit_price is None and data.event_type.upper() in ("DIP_AL", "SIGNAL", "PUSU"):
        boxes.append(("ANLIK", _fmt_price(data.price), (255, 255, 255)))

    if boxes:
        box_y = CARD_H - 150
        total_w = CARD_W - header_pad_x * 2
        gap = 14
        box_w = (total_w - gap * (len(boxes) - 1)) // len(boxes)
        box_h = 92
        for i, (label, value, color) in enumerate(boxes):
            x0 = header_pad_x + i * (box_w + gap)
            x1 = x0 + box_w
            _rounded_rect(draw, (x0, box_y, x1, box_y + box_h), radius=14,
                          fill=(0, 0, 0, 80))
            # Gerçekten yarı-saydam olması için overlay kullanalım
            overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            od.rounded_rectangle((0, 0, box_w, box_h), radius=14, fill=(0, 0, 0, 110))
            img.paste(overlay, (x0, box_y), overlay)
            draw = ImageDraw.Draw(img)
            draw.text((x0 + 16, box_y + 12), label,
                      font=_font(18, bold=True), fill=(255, 255, 255, 190))
            draw.text((x0 + 16, box_y + 38), value,
                      font=_font(30, bold=True), fill=color)

    # ---- Alt satır: R:R, süre, tarihler ----
    foot_y = CARD_H - 42
    pieces = []
    if data.rr is not None:
        pieces.append(f"R:R  {data.rr:.2f}".replace(".", ","))
    if data.duration:
        pieces.append(f"Süre: {data.duration}")
    if data.opened_at:
        pieces.append(f"Açılış: {data.opened_at}")
    if data.closed_at:
        pieces.append(f"Kapanış: {data.closed_at}")
    foot_text = "   •   ".join(pieces) if pieces else datetime.now().strftime("%d.%m.%Y %H:%M")
    draw.text((header_pad_x, foot_y - 6), foot_text,
              font=_font(18, bold=True), fill=(255, 255, 255, 200))

    # Sağ alt köşe: "İŞLEM ALINDI" / "HEDEF OK" benzeri durum rozeti
    status_badge = _status_badge_text(data)
    if status_badge:
        sb_font = _font(20, bold=True)
        bbox = draw.textbbox((0, 0), status_badge, font=sb_font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        bx1 = CARD_W - header_pad_x
        bx0 = bx1 - bw - 28
        by0 = foot_y - 14
        by1 = by0 + bh + 16
        _rounded_rect(draw, (bx0, by0, bx1, by1), radius=10, fill=theme["accent"])
        draw.text((bx0 + 14, by0 + 6), status_badge,
                  font=sb_font, fill=(20, 30, 40))

    return img


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
    """Kartı üret ve PNG olarak kaydet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = render_card(data)
    img.save(path, "PNG", optimize=True)
    return path


def build_caption(data: CardData) -> str:
    """Telegram sendPhoto caption'u için kısa metin (kart yanında görünür)."""
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
