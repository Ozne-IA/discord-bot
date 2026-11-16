"""Génération d'images (Pillow) : captcha de vérification et carte de rang."""
from __future__ import annotations

import io
import random
import string
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Caractères sans ambiguïté (pas de 0/O, 1/I/l…)
CAPTCHA_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL5S2Z8B")
FONT_CANDIDATES = ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]


@lru_cache(maxsize=16)
def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  Captcha
# --------------------------------------------------------------------------- #
def new_captcha_code(length: int = 5) -> str:
    return "".join(random.SystemRandom().choice(CAPTCHA_ALPHABET) for _ in range(length))


def captcha_image(code: str) -> bytes:
    w, h = 300, 110
    rnd = random.Random()
    img = Image.new("RGB", (w, h), (rnd.randint(225, 245), rnd.randint(225, 245), rnd.randint(225, 245)))
    draw = ImageDraw.Draw(img)
    # bruit de fond
    for _ in range(900):
        draw.point((rnd.randrange(w), rnd.randrange(h)), fill=(rnd.randint(120, 210),) * 3)
    for _ in range(6):
        draw.line([(rnd.randrange(w), rnd.randrange(h)) for _ in range(2)],
                  fill=(rnd.randint(90, 180), rnd.randint(90, 180), rnd.randint(90, 180)), width=2)
    # lettres tournées une par une
    x = 22
    for ch in code:
        size = rnd.randint(46, 58)
        tile = Image.new("RGBA", (size + 20, size + 24), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((8, 4), ch, font=font(size),
                                  fill=(rnd.randint(10, 90), rnd.randint(10, 90), rnd.randint(60, 140), 255))
        tile = tile.rotate(rnd.uniform(-28, 28), resample=Image.Resampling.BICUBIC, expand=True)
        img.paste(tile, (x, rnd.randint(4, 24)), tile)
        x += rnd.randint(46, 54)
    # ligne qui barre le texte
    y = rnd.randint(40, 70)
    draw.line([(0, y), (w, y + rnd.randint(-25, 25))], fill=(60, 60, 90), width=3)
    return _png(img.filter(ImageFilter.SMOOTH))


# --------------------------------------------------------------------------- #
#  Carte de bienvenue
# --------------------------------------------------------------------------- #
def _fit(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: int):
    """Réduit la taille de police (puis coupe) pour que le texte tienne dans la largeur."""
    while size > 18 and draw.textlength(text, font=font(size)) > max_width:
        size -= 2
    f = font(size)
    while text and draw.textlength(text, font=f) > max_width:
        text = text[:-2] + "…"
    return text, f


def welcome_card(name: str, avatar: bytes | None, server: str, number: int, color: int = 0x5865F2,
                 title: str = "BIENVENUE", subtitle: str = "Membre n°{}") -> bytes:
    w, h = 1024, 450
    accent = _hex_to_rgb(color)
    card = Image.new("RGB", (w, h), (20, 22, 28))
    draw = ImageDraw.Draw(card)
    # dégradé diagonal discret aux couleurs du serveur
    for y in range(h):
        a = 0.55 * (1 - y / h)
        shade = tuple(int(base + c * a * 0.5) for base, c in zip((20, 22, 28), accent, strict=True))
        draw.line([(0, y), (w, y)], fill=shade)
    for i in range(14):
        r = 30 + i * 22
        draw.ellipse([w - 120 - r, -80 - r, w - 120 + r, -80 + r], outline=(*accent, ), width=1)
    draw.rounded_rectangle([16, 16, w - 16, h - 16], radius=30, outline=(50, 54, 66), width=2)

    size = 190
    if avatar:
        try:
            av = Image.open(io.BytesIO(avatar)).convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            av = Image.new("RGB", (size, size), accent)
    else:
        av = Image.new("RGB", (size, size), accent)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    cx, cy = w // 2, 140
    draw.ellipse([cx - size // 2 - 8, cy - size // 2 - 8, cx + size // 2 + 8, cy + size // 2 + 8], fill=accent)
    card.paste(av, (cx - size // 2, cy - size // 2), mask)

    draw.text((cx, 268), title, font=font(30), fill=accent, anchor="mm")
    text, f = _fit(draw, name, 56, w - 120)
    draw.text((cx, 322), text, font=f, fill=(242, 243, 245), anchor="mm")
    sub, f2 = _fit(draw, f"{server} • " + subtitle.format(number), 28, w - 160)
    draw.text((cx, 382), sub, font=f2, fill=(181, 186, 199), anchor="mm")
    return _png(card)


def og_banner(name: str, avatar: bytes | None, tagline: str, footer: str) -> bytes:
    """Image d'aperçu (1200×630) affichée quand on partage le lien du site sur Discord, X, etc."""
    w, h = 1200, 630
    accent = (88, 101, 242)
    img = Image.new("RGB", (w, h), (15, 17, 23))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        a = 0.6 * (1 - y / h)
        draw.line([(0, y), (w, y)], fill=tuple(int(b + c * a * 0.45) for b, c in zip((15, 17, 23), accent, strict=True)))
    for i in range(16):
        r = 40 + i * 26
        draw.ellipse([w - 140 - r, h + 60 - r, w - 140 + r, h + 60 + r], outline=accent, width=1)
    size = 220
    try:
        av = Image.open(io.BytesIO(avatar)).convert("RGB").resize((size, size), Image.Resampling.LANCZOS) if avatar else None
    except Exception:
        av = None
    av = av or Image.new("RGB", (size, size), accent)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    x0, y0 = 90, (h - size) // 2 - 30
    draw.ellipse([x0 - 8, y0 - 8, x0 + size + 8, y0 + size + 8], fill=accent)
    img.paste(av, (x0, y0), mask)
    left = x0 + size + 60
    text, f = _fit(draw, name, 76, w - left - 60)
    draw.text((left, 210), text, font=f, fill=(242, 243, 245), anchor="lm")
    line, f2 = _fit(draw, tagline, 36, w - left - 60)
    draw.text((left, 290), line, font=f2, fill=(181, 186, 199), anchor="lm")
    foot, f3 = _fit(draw, footer, 28, w - left - 60)
    draw.text((left, 360), foot, font=f3, fill=(121, 131, 245), anchor="lm")
    return _png(img)


# --------------------------------------------------------------------------- #
#  Carte de rang
# --------------------------------------------------------------------------- #
def _hex_to_rgb(color: int) -> tuple[int, int, int]:
    return (color >> 16) & 255, (color >> 8) & 255, color & 255


def rank_card(name: str, avatar: bytes | None, level: int, rank: int, current: int, needed: int,
              total_xp: int, messages: int, color: int = 0x5865F2) -> bytes:
    w, h = 934, 282
    accent = _hex_to_rgb(color)
    card = Image.new("RGB", (w, h), (24, 26, 33))
    draw = ImageDraw.Draw(card)
    # bandeau dégradé discret
    for i in range(w):
        a = int(40 * (1 - i / w))
        draw.line([(i, 0), (i, h)], fill=(24 + accent[0] * a // 255, 26 + accent[1] * a // 255, 33 + accent[2] * a // 255))
    draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=26, outline=(48, 52, 64), width=2)

    # avatar rond
    size = 190
    if avatar:
        try:
            av = Image.open(io.BytesIO(avatar)).convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            av = Image.new("RGB", (size, size), accent)
    else:
        av = Image.new("RGB", (size, size), accent)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    draw.ellipse([40 - 6, 46 - 6, 40 + size + 6, 46 + size + 6], fill=accent)
    card.paste(av, (40, 46), mask)

    # textes
    left = 270
    name_font = font(44)
    max_width = (w - 50 - 250) - left  # place laissée au bloc niveau / rang à droite
    display = name
    while display and draw.textlength(display, font=name_font) > max_width:
        display = display[:-1]
    if display != name:
        display = display[:-1] + "…"
    draw.text((left, 70), display, font=name_font, fill=(242, 243, 245))
    draw.text((w - 50, 40), f"NIVEAU {level}", font=font(40), fill=accent, anchor="ra")
    draw.text((w - 50, 92), f"RANG #{rank}", font=font(28), fill=(181, 186, 199), anchor="ra")

    # barre de progression
    bx0, by0, bx1, by1 = left, 160, w - 50, 202
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=21, fill=(48, 52, 64))
    ratio = max(0.0, min(1.0, current / needed if needed else 1))
    if ratio > 0:
        draw.rounded_rectangle([bx0, by0, bx0 + max(42, int((bx1 - bx0) * ratio)), by1], radius=21, fill=accent)
    draw.text((bx1, 128), f"{current:,} / {needed:,} XP".replace(",", " "), font=font(24),
              fill=(181, 186, 199), anchor="ra")
    draw.text((left, 222), f"{total_xp:,} XP au total  •  {messages:,} messages".replace(",", " "),
              font=font(22), fill=(130, 136, 150))
    return _png(card)
