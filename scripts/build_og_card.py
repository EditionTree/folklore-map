#!/usr/bin/env python3
"""Rebuild the social share (OpenGraph) card from the live hero's own assets.

Mirrors the homepage hero so the share preview and the page stay in step:
the nautical chart at .6 opacity positioned 61%, the hero's 90deg scrim,
the tree emblem with its warm glow, Marcellus title + Spectral-italic tagline.

Writes og/preview-folklore-finder.jpg (and og/preview.jpg, the generator's
fallback for entries without their own hero art).

  python scripts/build_og_card.py

Nudge LEFT_MARGIN / the Y_* values below to re-compose; re-run to regenerate.
"""
import io
import os
import re
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── canvas / palette (matches folklorefinder.css hero tokens) ──────────────
W, H = 1200, 630                     # OpenGraph standard (1.91:1)
NIGHT = (29, 23, 18)                 # --ff-night
GOLD = (176, 144, 96)                # --ff-antique-gold
CREAM = (242, 232, 213)              # .hero-title colour

# ── layout ────────────────────────────────────────────────────────────────
LEFT_MARGIN = 100                    # breathing room from the left edge
Y_EYEBROW, Y_EMBLEM, Y_TITLE, Y_TAGLINE = 186, 220, 330, 428
EMBLEM_PX = 88

EYEBROW = "A LIVING ARCHIVE OF BRITAIN & IRELAND"
TITLE = "Folklore Finder"
TAGLINE = "An atlas of myths, legends, & stories"

FONT_DIR = "tmp/ogfonts"
FONTS = {                            # Pillow needs TTF; a legacy UA gets us TTF URLs
    "marcellus": "https://fonts.googleapis.com/css?family=Marcellus",
    "spectral-italic": "https://fonts.googleapis.com/css?family=Spectral:400italic",
}


def ensure_fonts():
    os.makedirs(FONT_DIR, exist_ok=True)
    for name, css_url in FONTS.items():
        dest = f"{FONT_DIR}/{name}.ttf"
        if os.path.isfile(dest):
            continue
        req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/4.0"})
        css = urllib.request.urlopen(req).read().decode()
        m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if not m:
            raise SystemExit(f"no TTF url for {name}")
        urllib.request.urlretrieve(m.group(1), dest)


def scrim_mask():
    """The hero's linear-gradient(90deg, .96 0%, .88 42%, .30 78%, .20 100%)."""
    stops = [(0.0, 0.96), (0.42, 0.88), (0.78, 0.30), (1.0, 0.20)]
    row = Image.new("L", (W, 1))
    px = row.load()
    for x in range(W):
        t = x / (W - 1)
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                f = (t - p0) / (p1 - p0) if p1 > p0 else 0
                px[x, 0] = int(round((a0 + (a1 - a0) * f) * 255))
                break
    return row.resize((W, H))


def tracked(draw, xy, text, font, fill, track):
    """Pillow has no letter-spacing, so step each glyph manually."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + track


def build():
    ensure_fonts()

    # chart: cover-fit, background-position 61% center, .6 opacity over night
    chart = Image.open("hero-nautical-chart.jpg").convert("RGB")
    cw, ch = chart.size
    scale = max(W / cw, H / ch)
    chart = chart.resize((int(cw * scale + 0.5), int(ch * scale + 0.5)), Image.LANCZOS)
    nw, nh = chart.size
    layer = Image.new("RGB", (W, H), NIGHT)
    layer.paste(chart, (int(-(nw - W) * 0.61), int(-(nh - H) * 0.5)))
    img = Image.blend(Image.new("RGB", (W, H), NIGHT), layer, 0.6)
    img = Image.composite(Image.new("RGB", (W, H), NIGHT), img, scrim_mask())
    img = img.convert("RGBA")

    # emblem + its warm glow (mirrors drop-shadow(0 4px 24px rgba(196,98,42,.5)))
    em = Image.open("green-man.png").convert("RGBA").resize((EMBLEM_PX, EMBLEM_PX), Image.LANCZOS)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    stamp = Image.new("RGBA", em.size, (196, 98, 42, 0))
    stamp.paste((196, 98, 42, 120), (0, 0), em)
    glow.paste(stamp, (LEFT_MARGIN, Y_EMBLEM + 4), stamp)
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(12)))
    img.paste(em, (LEFT_MARGIN, Y_EMBLEM), em)

    d = ImageDraw.Draw(img)
    f_eyebrow = ImageFont.truetype(f"{FONT_DIR}/marcellus.ttf", 15)
    f_title = ImageFont.truetype(f"{FONT_DIR}/marcellus.ttf", 76)
    f_tag = ImageFont.truetype(f"{FONT_DIR}/spectral-italic.ttf", 25)
    tracked(d, (LEFT_MARGIN, Y_EYEBROW), EYEBROW, f_eyebrow, GOLD, 2.7)      # .18em
    tracked(d, (LEFT_MARGIN, Y_TITLE), TITLE, f_title, CREAM, 1.9)           # .025em
    tracked(d, (LEFT_MARGIN, Y_TAGLINE), TAGLINE, f_tag, GOLD + (217,), 1.0)  # .04em

    # JPEG: the chart makes PNG ~700KB. quality 92 + 4:4:4 keeps the title's
    # edges crisp (chroma subsampling smears large text).
    out = img.convert("RGB")
    for path in ("og/preview-folklore-finder.jpg", "og/preview.jpg"):
        out.save(path, "JPEG", quality=92, optimize=True, progressive=True, subsampling=0)
        print(f"wrote {path} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    build()
