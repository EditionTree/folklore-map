# -*- coding: utf-8 -*-
"""
Folklore Finder — Field Guide generator (v2).

`python scripts/build_field_guide.py <collection-slug>` builds an A4, print-ready
PDF field guide for any themed collection, pulling live content from
collections.json + legends.json and the legend hero images. Designed as a
reusable, collection-agnostic template: only the data changes.

Design goals (v2): a crafted, collectible feel — aged-parchment texture, line-art
symbols, an ornamented book cover, drop-caps, framed & vignetted art, wax-seal
stamps — plus value the map can't give (a "Reading the Signs" motif decoder and an
"In the Field" companion with a sightings log).

Deps: reportlab, matplotlib+numpy, Pillow (all present). Fonts in
_fieldguide_build/fonts; cached coastline _fieldguide_build/britain-outline.geojson.
"""
from __future__ import annotations
import json, io, os, re, sys, unicodedata, math
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
FG = ROOT / "_fieldguide_build"
FONTS = FG / "fonts"
OUTLINE = FG / "britain-outline.geojson"
PAPER = FG / "paper-texture.png"
VIGNETTE = FG / "vignette.png"
OUT_DIR = ROOT / "output" / "pdf"
SITE = "folklorefinder.uk"
FIELD_ICON_DIR = ROOT / "assets" / "field-guide" / "marks"

# ── palette ────────────────────────────────────────────────────────────────
INK       = HexColor("#2c1f0e")
INK_LIGHT = HexColor("#5c4a2a")
PARCH     = HexColor("#efe4cb")
PARCH_DK  = HexColor("#e2d2b0")
DARK      = HexColor("#160b04")
ACCENT    = HexColor("#8b3a1a")
ACCENT_W  = HexColor("#c4622a")
WAX       = HexColor("#8a2b17")
GOLD      = HexColor("#b09060")
GOLD_SOFT = HexColor("#cdb488")
CREAM     = HexColor("#f6f1e6")

W, H = A4
MARGIN = 48

DISP = "Marcellus"
BODY = "Spectral"
BODY_MED = "Spectral-Med"
BODY_SB = "Spectral-SB"
BODY_IT = "Spectral-It"

ICON_IMAGE_FOR = {
    "book": "book.png",
    "scroll": "feather.png",
    "pin": "distribution.png",
    "feather": "feather.png",
    "eye": "dog.png",
    "signpost": "signpost.png",
    "paw": "boot.png",
    "check": "check.png",
    "hourglass": "hourglass.png",
    "moon": "moon.png",
    "flame": "flame.png",
    "chain": "flame.png",
    "compass": "compass.png",
    "map": "map.png",
    "distribution": "distribution.png",
    "dog": "dog.png",
    "boot": "boot.png",
}


def register_fonts():
    reg = {DISP: "Marcellus-Regular.ttf", BODY: "Spectral-Regular.ttf",
           BODY_MED: "Spectral-Medium.ttf", BODY_SB: "Spectral-SemiBold.ttf",
           BODY_IT: "Spectral-Italic.ttf"}
    if all((FONTS / fn).exists() for fn in reg.values()):
        for n, fn in reg.items():
            pdfmetrics.registerFont(TTFont(n, str(FONTS / fn)))
    else:
        for n, fn in [(DISP, "georgiab.ttf"), (BODY, "georgia.ttf"), (BODY_MED, "georgia.ttf"),
                      (BODY_SB, "georgiab.ttf"), (BODY_IT, "georgiai.ttf")]:
            pdfmetrics.registerFont(TTFont(n, r"C:\Windows\Fonts\%s" % fn))


def ensure_assets():
    """Generate the paper texture + vignette overlay once (cached)."""
    import numpy as np
    from PIL import Image
    if not PAPER.exists():
        h, w = 1273, 900
        rng = np.random.default_rng(7)
        img = np.tile(np.array([236, 226, 204], float), (h, w, 1))
        img += rng.normal(0, 4.6, (h, w, 1))
        img += rng.normal(0, 1.8, (h, w, 1))
        yy, xx = np.mgrid[0:h, 0:w]
        for _ in range(8):
            sx, sy = rng.uniform(0, w), rng.uniform(0, h)
            r, amp = rng.uniform(70, 190), rng.uniform(4, 9)
            img -= (amp * np.exp(-(((xx - sx) ** 2 + (yy - sy) ** 2) / (r * r))))[..., None]
        cx, cy = w / 2, h / 2
        d = np.sqrt(((xx - cx) / (w * 0.62)) ** 2 + ((yy - cy) / (h * 0.62)) ** 2)
        img *= np.clip(1 - 0.11 * np.clip(d - 0.5, 0, 1), 0.88, 1)[..., None]
        Image.fromarray(np.clip(img, 0, 255).astype("uint8")).save(PAPER)
    if not VIGNETTE.exists():
        h = w = 600
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        a = (np.clip((d - 0.5) / 0.7, 0, 1) ** 1.7 * 155).astype("uint8")
        rgba = np.dstack([np.full((h, w), 18, "uint8"), np.full((h, w), 10, "uint8"),
                          np.full((h, w), 4, "uint8"), a])
        Image.fromarray(rgba, "RGBA").save(VIGNETTE)


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


NATIONS = {"england", "scotland", "wales", "ireland", "northern-ireland",
           "isle-of-man", "channel-islands", "guernsey", "jersey", "cornwall"}


def motifs_of(m):
    reg = (m.get("region", "") or "").lower()
    out = [t for t in (m.get("tags") or [])
           if t not in ("dog", "black") and t not in NATIONS and t.replace("-", " ") not in reg]
    return ", ".join(out) if out else "—"


def short_region(region):
    return (region or "").split(",")[0].strip()


def hero_image_path(slug):
    """Return the best available hero image for a legend slug."""
    for ext in (".jpg", ".webp", ".png", ".jpeg"):
        p = ROOT / "legend-images" / ("%s-hero%s" % (slug, ext))
        if p.exists():
            return p
    return ROOT / "legend-images" / ("%s-hero.jpg" % slug)


# ── text helpers ────────────────────────────────────────────────────────────
def wrap(text, font, size, max_w):
    words = re.sub(r"\s+", " ", text or "").strip().split(" ")
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if pdfmetrics.stringWidth(t, font, size) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def para(c, text, x, y, max_w, font=BODY, size=10.5, leading=15, color=INK, align="left"):
    c.setFillColor(color); c.setFont(font, size)
    for ln in wrap(text, font, size, max_w):
        if align == "center":
            c.drawCentredString(x + max_w / 2, y, ln)
        elif align == "justify":
            _justify(c, ln, x, y, max_w, font, size, last=(ln == wrap(text, font, size, max_w)[-1]))
        else:
            c.drawString(x, y, ln)
        y -= leading
    return y


def _justify(c, line, x, y, max_w, font, size, last=False):
    words = line.split(" ")
    if last or len(words) == 1:
        c.drawString(x, y, line); return
    tw = sum(pdfmetrics.stringWidth(w, font, size) for w in words)
    gap = (max_w - tw) / (len(words) - 1)
    cx = x
    for w in words:
        c.drawString(cx, y, w); cx += pdfmetrics.stringWidth(w, font, size) + gap


def dropcap(c, text, x, y, w, font=BODY, size=10.5, leading=15.5, color=INK, cap_color=ACCENT):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return y
    cap, rest = text[0].upper(), text[1:]
    cs = size * 2.7
    c.setFont(DISP, cs); c.setFillColor(cap_color)
    c.drawString(x, y - leading * 1.15, cap)
    cap_w = pdfmetrics.stringWidth(cap, DISP, cs) + 7
    lines, cur = [], ""
    for wd in rest.split(" "):
        mw = (w - cap_w) if len(lines) < 2 else w
        t = (cur + " " + wd).strip()
        if pdfmetrics.stringWidth(t, font, size) <= mw:
            cur = t
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    c.setFont(font, size); c.setFillColor(color)
    yy = y
    for i, ln in enumerate(lines):
        c.drawString(x + (cap_w if i < 2 else 0), yy, ln); yy -= leading
    return yy


def tracked(c, s, x, y, font, size, color, tr=2.0, center_w=None):
    c.setFont(font, size); c.setFillColor(color)
    total = sum(pdfmetrics.stringWidth(ch, font, size) + tr for ch in s) - tr
    if center_w is not None:
        x = x + (center_w - total) / 2
    for ch in s:
        c.drawString(x, y, ch); x += pdfmetrics.stringWidth(ch, font, size) + tr
    return x


def dbl_rule(c, x, y, w, color=GOLD, diamond=True):
    c.setStrokeColor(color); c.setLineWidth(0.8); c.line(x, y, x + w, y)
    c.setLineWidth(0.4); c.line(x, y - 2.4, x + w, y - 2.4)


def eyebrow(c, s, x, y, w, color=ACCENT, icon=None):
    c.setFont(DISP, 9.5)
    tw = sum(pdfmetrics.stringWidth(ch, DISP, 9.5) + 2.2 for ch in s) - 2.2
    cx = x + w / 2
    c.setStrokeColor(GOLD); c.setLineWidth(0.8)
    c.line(x + 8, y + 3, cx - tw / 2 - 14, y + 3)
    c.line(cx + tw / 2 + 14, y + 3, x + w - 8, y + 3)
    tracked(c, s, cx - tw / 2, y, DISP, 9.5, color, tr=2.2)


# ── icon library (crisp line art) ───────────────────────────────────────────
def _ic(c, color, lw=1.15):
    c.setStrokeColor(color); c.setLineWidth(lw); c.setLineCap(1); c.setLineJoin(1)


def _book(c, x, y, s, col):
    _ic(c, col); m = x + s / 2
    c.line(m, y + .16 * s, m, y + .84 * s)
    for sgn in (-1, 1):
        p = c.beginPath(); p.moveTo(m, y + .84 * s)
        p.curveTo(m + sgn * .22 * s, y + .74 * s, m + sgn * .40 * s, y + .76 * s, m + sgn * .44 * s, y + .80 * s)
        p.lineTo(m + sgn * .44 * s, y + .22 * s)
        p.curveTo(m + sgn * .40 * s, y + .18 * s, m + sgn * .22 * s, y + .16 * s, m, y + .28 * s)
        c.drawPath(p, stroke=1, fill=0)


def _scroll(c, x, y, s, col):
    _ic(c, col)
    c.roundRect(x + .18 * s, y + .24 * s, .64 * s, .52 * s, .04 * s, stroke=1, fill=0)
    for yy in (y + .78 * s, y + .22 * s):
        c.ellipse(x + .12 * s, yy - .05 * s, x + .30 * s, yy + .05 * s, stroke=1, fill=0)
        c.ellipse(x + .70 * s, yy - .05 * s, x + .88 * s, yy + .05 * s, stroke=1, fill=0)
    for i in range(3):
        c.line(x + .30 * s, y + (.60 - i * .12) * s, x + .70 * s, y + (.60 - i * .12) * s)


def _pin(c, x, y, s, col):
    _ic(c, col); cx = x + s / 2
    c.circle(cx, y + .60 * s, .26 * s, stroke=1, fill=0)
    c.circle(cx, y + .60 * s, .09 * s, stroke=0, fill=1) if False else c.circle(cx, y + .60 * s, .08 * s, stroke=1, fill=0)
    p = c.beginPath(); p.moveTo(cx - .18 * s, y + .48 * s); p.lineTo(cx, y + .12 * s); p.lineTo(cx + .18 * s, y + .48 * s)
    c.drawPath(p, stroke=1, fill=0)


def _feather(c, x, y, s, col):
    _ic(c, col)
    p = c.beginPath(); p.moveTo(x + .22 * s, y + .18 * s); p.curveTo(x + .30 * s, y + .55 * s, x + .55 * s, y + .78 * s, x + .82 * s, y + .84 * s)
    c.drawPath(p, stroke=1, fill=0)
    p = c.beginPath(); p.moveTo(x + .22 * s, y + .18 * s); p.curveTo(x + .55 * s, y + .30 * s, x + .74 * s, y + .55 * s, x + .82 * s, y + .84 * s)
    c.drawPath(p, stroke=1, fill=0)
    for t in (.42, .55, .68):
        c.line(x + (.30 + (t - .42)) * s, y + (t) * s, x + (.55) * s, y + (t + .06) * s)
    c.line(x + .22 * s, y + .18 * s, x + .12 * s, y + .10 * s)


def _eye(c, x, y, s, col):
    _ic(c, col); cx, cy = x + s / 2, y + s / 2
    p = c.beginPath(); p.moveTo(x + .10 * s, cy); p.curveTo(x + .30 * s, y + .82 * s, x + .70 * s, y + .82 * s, x + .90 * s, cy)
    p.curveTo(x + .70 * s, y + .18 * s, x + .30 * s, y + .18 * s, x + .10 * s, cy); c.drawPath(p, stroke=1, fill=0)
    c.circle(cx, cy, .16 * s, stroke=1, fill=0); c.setFillColor(col); c.circle(cx, cy, .06 * s, stroke=0, fill=1)


def _signpost(c, x, y, s, col):
    _ic(c, col); cx = x + .42 * s
    c.line(cx, y + .12 * s, cx, y + .86 * s)
    for yy, dr in ((.70, 1), (.50, -1)):
        if dr > 0:
            p = c.beginPath(); p.moveTo(cx, y + (yy + .09) * s); p.lineTo(x + .84 * s, y + (yy + .09) * s)
            p.lineTo(x + .92 * s, y + yy * s); p.lineTo(x + .84 * s, y + (yy - .09) * s); p.lineTo(cx, y + (yy - .09) * s); p.close()
        else:
            p = c.beginPath(); p.moveTo(cx, y + (yy + .09) * s); p.lineTo(x + .16 * s, y + (yy + .09) * s)
            p.lineTo(x + .08 * s, y + yy * s); p.lineTo(x + .16 * s, y + (yy - .09) * s); p.lineTo(cx, y + (yy - .09) * s); p.close()
        c.drawPath(p, stroke=1, fill=0)


def _paw(c, x, y, s, col):
    _ic(c, col); c.setFillColor(col)
    c.ellipse(x + .34 * s, y + .16 * s, x + .66 * s, y + .48 * s, stroke=1, fill=0)
    for dx in (.20, .40, .60, .80):
        c.circle(x + dx * s, y + (.66 if dx in (.40, .60) else .58) * s, .085 * s, stroke=1, fill=0)


def _check(c, x, y, s, col):
    _ic(c, col)
    c.roundRect(x + .14 * s, y + .14 * s, .72 * s, .72 * s, .06 * s, stroke=1, fill=0)
    _ic(c, ACCENT_W, 1.6)
    p = c.beginPath(); p.moveTo(x + .30 * s, y + .50 * s); p.lineTo(x + .45 * s, y + .32 * s); p.lineTo(x + .74 * s, y + .70 * s)
    c.drawPath(p, stroke=1, fill=0)


def _hourglass(c, x, y, s, col):
    _ic(c, col)
    c.line(x + .22 * s, y + .84 * s, x + .78 * s, y + .84 * s); c.line(x + .22 * s, y + .16 * s, x + .78 * s, y + .16 * s)
    p = c.beginPath(); p.moveTo(x + .24 * s, y + .84 * s); p.lineTo(x + .76 * s, y + .84 * s)
    p.lineTo(x + .52 * s, y + .50 * s); p.lineTo(x + .76 * s, y + .16 * s); p.lineTo(x + .24 * s, y + .16 * s)
    p.lineTo(x + .48 * s, y + .50 * s); p.close(); c.drawPath(p, stroke=1, fill=0)


def _moon(c, x, y, s, col):
    _ic(c, col); cx, cy = x + s / 2, y + s / 2
    c.circle(cx, cy, .34 * s, stroke=1, fill=0)
    c.setFillColor(PARCH); c.circle(cx + .14 * s, cy + .06 * s, .30 * s, stroke=0, fill=1)
    _ic(c, col); c.saveState(); p = c.beginPath()
    p.arc(cx - .34 * s, cy - .34 * s, cx + .34 * s, cy + .34 * s, 40, 280); c.drawPath(p, stroke=1, fill=0); c.restoreState()


def _flame(c, x, y, s, col):
    _ic(c, col)
    p = c.beginPath(); p.moveTo(x + .5 * s, y + .12 * s)
    p.curveTo(x + .16 * s, y + .34 * s, x + .34 * s, y + .58 * s, x + .40 * s, y + .70 * s)
    p.curveTo(x + .44 * s, y + .56 * s, x + .52 * s, y + .52 * s, x + .54 * s, y + .40 * s)
    p.curveTo(x + .70 * s, y + .56 * s, x + .70 * s, y + .74 * s, x + .58 * s, y + .88 * s)
    p.curveTo(x + .86 * s, y + .74 * s, x + .90 * s, y + .40 * s, x + .5 * s, y + .12 * s); c.drawPath(p, stroke=1, fill=0)


def _chain(c, x, y, s, col):
    _ic(c, col)
    for i in range(3):
        c.ellipse(x + (.14 + i * .24) * s, y + .38 * s, x + (.34 + i * .24) * s, y + .62 * s, stroke=1, fill=0)


def _compass(c, x, y, s, col):
    _ic(c, col); cx, cy = x + s / 2, y + s / 2
    c.circle(cx, cy, .40 * s, stroke=1, fill=0)
    c.setFillColor(col)
    for a in (90, 0, 270, 180):
        r = math.radians(a); ex, ey = cx + .34 * s * math.cos(r), cy + .34 * s * math.sin(r)
        pr = math.radians(a + 90); px, py = cx + .09 * s * math.cos(pr), cy + .09 * s * math.sin(pr)
        pr2 = math.radians(a - 90); qx, qy = cx + .09 * s * math.cos(pr2), cy + .09 * s * math.sin(pr2)
        p = c.beginPath(); p.moveTo(ex, ey); p.lineTo(px, py); p.lineTo(qx, qy); p.close()
        c.drawPath(p, stroke=0, fill=1)


ICONS = {"book": _book, "scroll": _scroll, "pin": _pin, "feather": _feather, "eye": _eye,
         "signpost": _signpost, "paw": _paw, "check": _check, "hourglass": _hourglass,
         "moon": _moon, "flame": _flame, "chain": _chain, "compass": _compass}


PLACEHOLDER = Color(0.50, 0.42, 0.30, 0.40)


def field_icon_path(name):
    fn = ICON_IMAGE_FOR.get(name, "book.webp")
    return FIELD_ICON_DIR / fn


def icon(c, name, x, y, s, col=ACCENT):
    """Draw a small generated field-guide mark inline with text."""
    c.saveState()
    c.setDash()
    p = field_icon_path(name)
    if p.exists():
        c.drawImage(str(p), x, y, s, s, mask="auto")
    else:
        c.setFillColor(Color(0.86, 0.76, 0.56, 0.58))
        c.setStrokeColor(Color(0.58, 0.40, 0.20, 0.70))
        c.setLineWidth(0.65)
        c.roundRect(x, y, s, s, max(2, s * 0.12), stroke=0, fill=1)
    c.restoreState()


def wax_seal(c, cx, cy, r, glyph="paw"):
    """Draw a larger generated field-guide vignette."""
    s = r * 2.15
    icon(c, glyph, cx - s / 2, cy - s / 2, s, ACCENT)


# ── image + background ───────────────────────────────────────────────────────
def fit_image(c, path, x, y, w, h, radius=0):
    try:
        img = ImageReader(str(path)); iw, ih = img.getSize()
    except Exception:
        archive_plate(c, x, y, w, h, radius)
        return
    scale = max(w / iw, h / ih); dw, dh = iw * scale, ih * scale
    c.saveState(); p = c.beginPath()
    p.roundRect(x, y, w, h, radius) if radius else p.rect(x, y, w, h)
    c.clipPath(p, stroke=0, fill=0)
    c.drawImage(img, x - (dw - w) / 2, y - (dh - h) / 2, dw, dh, mask="auto"); c.restoreState()


def framed_image(c, path, x, y, w, h, radius=3):
    # Mounted art plate with a soft shadow and vignette.
    c.saveState()
    c.setDash()
    c.setFillColor(Color(0.20, 0.13, 0.07, 0.18))
    c.roundRect(x + 3, y - 3, w, h, radius + 2, stroke=0, fill=1)
    c.setFillColor(Color(0.96, 0.90, 0.76)); c.setStrokeColor(GOLD); c.setLineWidth(1.0)
    c.roundRect(x - 5, y - 5, w + 10, h + 10, radius + 4, stroke=1, fill=1)
    c.setStrokeColor(Color(0.43, 0.29, 0.14)); c.setLineWidth(0.7)
    c.roundRect(x - 1, y - 1, w + 2, h + 2, radius + 1, stroke=1, fill=0)
    fit_image(c, path, x, y, w, h, radius)
    if VIGNETTE.exists():
        c.drawImage(str(VIGNETTE), x, y, w, h, mask="auto")
    c.restoreState()


def archive_plate(c, x, y, w, h, radius=3):
    c.saveState()
    c.setDash()
    c.setFillColor(HexColor("#241a10"))
    c.roundRect(x, y, w, h, radius, stroke=0, fill=1)
    c.setStrokeColor(Color(0.74, 0.56, 0.34, 0.55)); c.setLineWidth(0.7)
    c.roundRect(x + 10, y + 10, w - 20, h - 20, max(1, radius), stroke=1, fill=0)
    s = min(w, h) * 0.22
    icon(c, "feather", x + w / 2 - s / 2, y + h / 2 - s / 2 + 12, s, GOLD_SOFT)
    tracked(c, "IMAGE TO ADD", x, y + h / 2 - 20, DISP, 8.5, GOLD_SOFT, 1.8, center_w=w)
    c.restoreState()


def page_bg(c, dark=False):
    if dark:
        c.setFillColor(DARK); c.rect(0, 0, W, H, stroke=0, fill=1)
    elif PAPER.exists():
        c.drawImage(str(PAPER), 0, 0, W, H)
    else:
        c.setFillColor(PARCH); c.rect(0, 0, W, H, stroke=0, fill=1)


def page_frame(c, col=GOLD, inset=30):
    """Draw the reusable page border and corner ornaments."""
    c.saveState()
    c.setDash()
    c.setStrokeColor(Color(0.70, 0.52, 0.30, 0.65)); c.setLineWidth(0.9)
    c.rect(inset, inset, W - 2 * inset, H - 2 * inset, stroke=1, fill=0)
    c.setStrokeColor(Color(0.70, 0.52, 0.30, 0.30)); c.setLineWidth(0.45)
    c.rect(inset + 6, inset + 6, W - 2 * (inset + 6), H - 2 * (inset + 6), stroke=1, fill=0)
    c.setStrokeColor(col); c.setLineWidth(1.0)
    l = 34
    for sx in (inset + 13, W - inset - 13):
        for sy in (inset + 13, H - inset - 13):
            dx = 1 if sx < W / 2 else -1
            dy = 1 if sy < H / 2 else -1
            c.line(sx, sy, sx + dx * l, sy)
            c.line(sx, sy, sx, sy + dy * l)
            c.circle(sx + dx * 7, sy + dy * 7, 2.2, stroke=1, fill=0)
    c.restoreState()


def footer(c, page_no, guide_name):
    c.setFont(BODY_IT, 8.5); c.setFillColor(INK_LIGHT)
    c.drawString(MARGIN, 24, "Folklore Finder Field Guide")
    c.drawRightString(W - MARGIN, 24, guide_name)
    c.setFont(DISP, 9); c.setFillColor(INK_LIGHT); c.drawCentredString(W / 2, 18, str(page_no))


# ── distribution map ─────────────────────────────────────────────────────────
def build_distribution_map(points, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, gold, accent, parch, land = "#2c1f0e", "#b09060", "#8b3a1a", "#efe4cb", "#ddcca6"
    geo = json.load(io.open(OUTLINE, encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(6.2, 8.2), dpi=220)
    fig.patch.set_facecolor(parch); ax.set_facecolor(parch)
    for f in geo["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ax.fill([p[0] for p in poly[0]], [p[1] for p in poly[0]],
                    facecolor=land, edgecolor=gold, linewidth=0.7, zorder=1)
    lats = [p[0] for p in points]; lngs = [p[1] for p in points]
    ax.scatter(lngs, lats, s=150, facecolor="none", edgecolor=accent, linewidth=0.5, zorder=2, alpha=0.35)
    ax.scatter(lngs, lats, s=64, color=accent, edgecolor=ink, linewidth=0.7, zorder=3, alpha=0.9)
    ax.set_xlim(-11.0, 2.6); ax.set_ylim(48.8, 61.4)
    ax.set_aspect(1.0 / math.cos(math.radians(54)))
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor(gold); sp.set_linewidth(1.3)
    ax.text(0.035, 0.975, "N", transform=ax.transAxes, fontsize=12, color=ink, fontweight="bold", va="top")
    ax.annotate("", xy=(0.045, 0.965), xytext=(0.045, 0.915), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=ink, lw=1.2))
    plt.tight_layout(pad=0.6); plt.savefig(out_png, facecolor=parch, bbox_inches="tight"); plt.close(fig)
    return out_png


# ── content loading ──────────────────────────────────────────────────────────
def load(slug):
    full = json.load(io.open(ROOT / "collections.json", encoding="utf-8"))
    col = next((c for c in full["collections"] if c["slug"] == slug), None)
    if not col:
        sys.exit("No collection '%s'" % slug)
    legs = {l["name"]: l for l in json.load(io.open(ROOT / "legends.json", encoding="utf-8"))["legends"]}
    members = []
    for nm in col.get("members", []):
        l = legs.get(nm)
        if not l:
            continue
        l = dict(l); l["_slug"] = slugify(nm)
        l["_img"] = hero_image_path(l["_slug"])
        members.append(l)
    return col, members


CAT = {"beast": "Beast", "ghost": "Ghost", "fairy": "Fae", "deity": "Deity", "dragon": "Dragon",
       "water": "Water Spirit", "giant": "Giant", "hero": "Legendary Figure", "witch": "Witch",
       "pirate": "Pirate", "location": "Place"}


def first_sentence(text, n=140):
    s = re.sub(r"\s+", " ", text or "").strip()
    m = re.search(r"(.+?[.!?])(\s|$)", s)
    q = (m.group(1) if m else s)
    return q if len(q) <= n else q[:n].rsplit(" ", 1)[0] + "…"


# ── pages ────────────────────────────────────────────────────────────────────
def cover(c, col, members):
    page_bg(c, dark=True)
    hero_name = col.get("hero_legend")
    hero = next((m for m in members if m["name"] == hero_name), members[0])
    cover_img = ROOT / col["cover_image"] if col.get("cover_image") else hero["_img"]
    # framed art plate, lower portion
    plate_x, plate_w = 64, W - 128
    plate_y, plate_h = 74, H * 0.44
    framed_image(c, cover_img, plate_x, plate_y, plate_w, plate_h, radius=2)
    page_frame(c, GOLD, inset=26)
    # masthead
    gm = ROOT / "green-man.png"
    if gm.exists():
        c.drawImage(str(gm), W / 2 - 20, H - 92, 40, 40, mask="auto")
    tracked(c, "FOLKLORE FINDER", 0, H - 116, DISP, 15, CREAM, 3.2, center_w=W)
    tracked(c, "FIELD GUIDE SERIES", 0, H - 133, DISP, 9.5, GOLD, 3.0, center_w=W)
    dbl_rule(c, W / 2 - 62, H - 150, 124, GOLD)
    tracked(c, "FIELD GUIDE No.1", 0, H - 182, DISP, 10, ACCENT_W, 3.0, center_w=W)
    # title
    title = col["title"]; main, sub = title, ""
    if " of " in title:
        main, sub = title.split(" of ", 1); sub = "of " + sub
    c.setFont(DISP, 50); c.setFillColor(CREAM); c.drawCentredString(W / 2, H - 244, main.upper())
    if sub:
        c.setFont(DISP, 25); c.setFillColor(GOLD_SOFT); c.drawCentredString(W / 2, H - 275, sub)
    tracked(c, "LEGENDS · SIGHTINGS · HISTORY · LOCATIONS", 0, H - 305, DISP, 9.5, GOLD, 2.2, center_w=W)
    wax_seal(c, W / 2, plate_y + plate_h + 30, 15, "dog")
    # foot tagline (over the plate base)
    c.setFont(BODY_IT, 11); c.setFillColor(Color(0.88, 0.81, 0.66))
    c.drawCentredString(W / 2, plate_y + 14, "A companion to the Folklore Finder Atlas")
    c.showPage()


SECTIONS = [
    ("Introduction", "Origins and meaning of the theme.", "book"),
    ("History & Folklore", "How the legends evolved over time.", "scroll"),
    ("Distribution Map", "Where the legends are reported.", "pin"),
    ("Reading the Signs", "How to know one when you meet it.", "eye"),
    ("Legend Profiles", "Individual stories from across the isles.", "feather"),
    ("Places to Visit", "Real locations linked to the legends.", "signpost"),
    ("In the Field", "A companion for your own searches.", "paw"),
    ("Explorer's Checklist", "Track the legends you've discovered.", "check"),
]


def about(c, col, members, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "ABOUT THIS GUIDE", MARGIN, y, W - 2 * MARGIN); y -= 28
    c.setFont(DISP, 25); c.setFillColor(INK); c.drawCentredString(W / 2, y, col["title"]); y -= 24
    y = para(c, col.get("intro", ""), MARGIN + 34, y, W - 2 * MARGIN - 68, BODY, 11, 16.5, INK_LIGHT, "center") - 12
    if col.get("context"):
        y = para(c, col["context"], MARGIN + 24, y, W - 2 * MARGIN - 48, BODY, 9.6, 14.5, INK) - 18
    dbl_rule(c, MARGIN + 70, y, W - 2 * MARGIN - 140, GOLD); y -= 26
    tracked(c, "WHAT'S INSIDE", 0, y, DISP, 13, ACCENT, 2.4, center_w=W); y -= 30
    colw = (W - 2 * MARGIN - 26) / 2
    ys = [y, y]
    for i, (title, desc, ic) in enumerate(SECTIONS):
        ci = i % 2; cx = MARGIN + ci * (colw + 26)
        icon(c, ic, cx, ys[ci] - 5, 20, ACCENT_W)
        c.setFillColor(INK); c.setFont(BODY_SB, 11.5); c.drawString(cx + 30, ys[ci], title)
        yy = para(c, desc, cx + 30, ys[ci] - 13, colw - 36, BODY, 9, 12.5, INK_LIGHT)
        ys[ci] = yy - 16
    yb = min(ys) - 4
    dbl_rule(c, MARGIN + 70, yb, W - 2 * MARGIN - 140, GOLD); yb -= 30
    chips = [("book", "12 PAGES", "PDF format"), ("signpost", "PRINT READY", "A4 optimised"),
             ("check", "FREE ON KO-FI", "Keep forever")]
    cw = (W - 2 * MARGIN) / 3
    for i, (ic, a, b) in enumerate(chips):
        cx = MARGIN + i * cw
        icon(c, ic, cx + cw / 2 - 9, yb + 4, 18, ACCENT)
        tracked(c, a, cx, yb - 14, DISP, 10.5, ACCENT, 1.5, center_w=cw)
        c.setFont(BODY_IT, 9); c.setFillColor(INK_LIGHT); c.drawCentredString(cx + cw / 2, yb - 27, b)
    footer(c, page_no, col["title"]); c.showPage()


def map_page(c, col, members, map_png, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "DISTRIBUTION MAP", MARGIN, y, W - 2 * MARGIN); y -= 26
    c.setFont(DISP, 22); c.setFillColor(INK); c.drawCentredString(W / 2, y, "Where the legends are found"); y -= 20
    y = para(c, "Every marker is a legend in this guide, placed where its story is rooted. "
                "Absence of a marker does not mean absence of a legend.",
             MARGIN + 55, y, W - 2 * MARGIN - 110, BODY_IT, 10, 14, INK_LIGHT, "center") - 6
    iw = ImageReader(str(map_png)); pw, ph = iw.getSize()
    boxw, boxh = W - 2 * MARGIN - 70, y - 118
    sc = min(boxw / pw, boxh / ph); dw, dh = pw * sc, ph * sc
    c.drawImage(iw, W / 2 - dw / 2, 100, dw, dh, mask="auto")
    c.setFillColor(ACCENT); c.setStrokeColor(INK); c.setLineWidth(0.7); c.circle(MARGIN + 8, 96, 4, stroke=1, fill=1)
    c.setFont(BODY, 9.5); c.setFillColor(INK)
    c.drawString(MARGIN + 20, 92, "Reported legend  ·  %d sites across Britain & Ireland" % len(members))
    footer(c, page_no, col["title"]); c.showPage()


SIGNS = [
    ("eye", "Eyes like coals", "Burning eyes — red, yellow, or 'the size of saucers' — are the surest mark. "
     "To meet that gaze was, in most tellings, to be marked for a death within the year."),
    ("dog", "Unnatural size", "Larger than any living dog; 'big as a calf' is the phrase used from Norfolk to the "
     "Highlands. Sheer size is what sets the spectral hound apart from a stray."),
    ("moon", "Silence & vanishing", "It makes little sound and leaves no track. It falls into step beside you, then is "
     "simply gone — most often at a boundary: a gate, a bridge, a stile."),
    ("signpost", "Thresholds & crossroads", "Black dogs keep to in-between places — parish bounds, old roads, lychgates and "
     "crossroads — the very ground where the living and the dead were thought to meet."),
    ("flame", "Chains & fire", "A dragging chain, a reek of sulphur, or a body wreathed in flame mark the more "
     "demonic hounds, especially in the tales of the south-west."),
    ("book", "Omen or guardian?", "Not every black dog brings death. Some, like the church grim, guard consecrated "
     "ground; others walk a lone traveller safely home. Read the errand, not just the beast."),
]


def signs_page(c, col, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "READING THE SIGNS", MARGIN, y, W - 2 * MARGIN); y -= 26
    c.setFont(DISP, 22); c.setFillColor(INK); c.drawCentredString(W / 2, y, "How to know one when you meet it"); y -= 18
    y = para(c, "The tradition is remarkably consistent across the islands. These are the marks "
                "that recur — the grammar of the black dog.", MARGIN + 55, y, W - 2 * MARGIN - 110,
             BODY_IT, 10, 14, INK_LIGHT, "center") - 14
    colw = (W - 2 * MARGIN - 30) / 2
    ys = [y, y]
    for i, (ic, title, body) in enumerate(SIGNS):
        ci = i % 2; cx = MARGIN + ci * (colw + 30)
        c.setFillColor(CREAM); c.setStrokeColor(GOLD); c.setLineWidth(0.8)
        # measure block height
        lines = wrap(body, BODY, 9.6, colw - 52)
        bh = 26 + len(lines) * 13.5 + 14
        c.roundRect(cx, ys[ci] - bh + 14, colw, bh, 4, stroke=1, fill=1)
        icon(c, ic, cx + 16, ys[ci] - 6, 22, ACCENT_W)
        c.setFillColor(ACCENT); c.setFont(DISP, 13); c.drawString(cx + 48, ys[ci], title)
        para(c, body, cx + 16, ys[ci] - 22, colw - 32, BODY, 9.6, 13.5, INK)
        ys[ci] -= bh + 12
    footer(c, page_no, col["title"]); c.showPage()


def profile(c, m, guide, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "LEGEND PROFILE", MARGIN, y, W - 2 * MARGIN); y -= 28
    c.setFont(DISP, 30); c.setFillColor(INK); c.drawCentredString(W / 2, y, m["name"]); y -= 18
    tracked(c, (m.get("region", "") or "").upper(), 0, y, DISP, 9.5, ACCENT_W, 1.8, center_w=W); y -= 20
    img_h = 168
    framed_image(c, m["_img"], MARGIN, y - img_h, W - 2 * MARGIN, img_h, radius=3)
    y -= img_h + 26
    side_w = 170; story_w = W - 2 * MARGIN - side_w - 28
    sx = MARGIN; tx = MARGIN + story_w + 28
    wax_seal(c, sx + 8, y + 8, 12, "book")
    c.setFont(DISP, 13); c.setFillColor(ACCENT); c.drawString(sx + 28, y + 3, "The Story")
    story_y = dropcap(c, m.get("detail") or m.get("summary", ""), sx, y - 22, story_w, BODY, 10.5, 15.5, INK)
    # pull-quote
    story_y -= 6
    c.setStrokeColor(ACCENT_W); c.setLineWidth(2); c.line(sx, story_y + 8, sx, story_y - 20)
    para(c, "“" + first_sentence(m.get("summary", ""), 120) + "”", sx + 12, story_y, story_w - 12,
         BODY_IT, 11.5, 15, ACCENT)
    # sidebar
    top = y + 14; bot = min(story_y - 40, top - 150)
    c.setFillColor(CREAM); c.setStrokeColor(GOLD); c.setLineWidth(1); c.roundRect(tx, bot, side_w, top - bot, 4, stroke=1, fill=1)
    c.setFillColor(ACCENT_W); c.rect(tx, top - 3, side_w, 3, stroke=0, fill=1)
    yy = top - 20
    tracked(c, "AT A GLANCE", tx + 14, yy, DISP, 9.5, ACCENT, 1.6); yy -= 18
    for label, val in [("Region", m.get("region", "—")), ("Type", CAT.get(m.get("category", ""), "Legend")),
                       ("Also known as", ", ".join(m.get("alt_names", [])) or "—"), ("Motifs", motifs_of(m))]:
        c.setFont(DISP, 8); c.setFillColor(INK_LIGHT); c.drawString(tx + 14, yy, label.upper()); yy -= 12
        yy = para(c, str(val), tx + 14, yy, side_w - 28, BODY, 9.5, 12.5, INK) - 8
    yy -= 2; c.setStrokeColor(GOLD); c.setLineWidth(0.5); c.line(tx + 14, yy + 4, tx + side_w - 14, yy + 4); yy -= 11
    c.setFont(DISP, 8); c.setFillColor(INK_LIGHT); c.drawString(tx + 14, yy, "READ THE FULL LEGEND"); yy -= 12
    c.setFont(BODY_SB, 8.4); c.setFillColor(ACCENT); c.drawString(tx + 14, yy, "%s/legends/%s" % (SITE, m["_slug"]))
    footer(c, page_no, guide); c.showPage()


def places_page(c, col, members, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "PLACES TO VISIT", MARGIN, y, W - 2 * MARGIN); y -= 26
    c.setFont(DISP, 22); c.setFillColor(INK); c.drawCentredString(W / 2, y, "Walk the ground the stories haunt"); y -= 32
    # prefer place-anchored members (a specific place before the comma), distinct is fine
    picks = sorted(members, key=lambda m: (0 if "," in (m.get("region") or "") else 1))[:4]
    row_h = (y - 128) / len(picks)
    for m in picks:
        iw2 = 148
        framed_image(c, m["_img"], MARGIN, y - row_h + 16, iw2, row_h - 22, radius=3)
        tx = MARGIN + iw2 + 22
        c.setFont(DISP, 15); c.setFillColor(INK); c.drawString(tx, y - 14, m["name"])
        tracked(c, (m.get("region", "") or "").upper(), tx, y - 28, DISP, 8, ACCENT_W, 1.3)
        para(c, m.get("summary", ""), tx, y - 44, W - MARGIN - tx, BODY, 9.5, 13, INK)
        c.setFont(BODY_SB, 8.4); c.setFillColor(ACCENT); c.drawString(tx, y - row_h + 22, "%s/legends/%s" % (SITE, m["_slug"]))
        y -= row_h
    c.setFillColor(PARCH_DK); c.roundRect(MARGIN, 92, W - 2 * MARGIN, 40, 4, stroke=0, fill=1)
    tracked(c, "EXPLORER TIP", 0, 120, DISP, 9, ACCENT, 1.6, center_w=W)
    c.setFont(BODY_IT, 9.5); c.setFillColor(INK_LIGHT)
    c.drawCentredString(W / 2, 104, "Many sites are wild, remote or private. Stay safe, respect the land and follow local guidance.")
    footer(c, page_no, col["title"]); c.showPage()


FIELD = [
    ("moon", "When to look", "Dusk and the dead of night, and most of all the turning points of the year — "
     "the old fire-festivals, and the nights around a funeral or a storm."),
    ("signpost", "Where to look", "Lonely lanes and green roads, lychgates and churchyards, parish boundaries, "
     "bridges and the coast path. Black dogs keep to edges."),
    ("eye", "What to note", "The eyes, the size, the sound (or silence), and where it appears and vanishes. "
     "Mark the exact spot — the tradition is rooted in real places."),
    ("boot", "Field etiquette", "Never trespass; ask permission on private land. Don't go alone after dark, tell "
     "someone your route, and leave every site as you found it."),
]


def field_page(c, col, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "IN THE FIELD", MARGIN, y, W - 2 * MARGIN); y -= 26
    c.setFont(DISP, 22); c.setFillColor(INK); c.drawCentredString(W / 2, y, "A companion for your own searches"); y -= 26
    for ic, title, body in FIELD:
        icon(c, ic, MARGIN, y - 6, 22, ACCENT_W)
        c.setFont(DISP, 13); c.setFillColor(ACCENT); c.drawString(MARGIN + 34, y, title)
        y = para(c, body, MARGIN + 34, y - 15, W - 2 * MARGIN - 34, BODY, 10, 14, INK) - 16
    y -= 4
    dbl_rule(c, MARGIN + 60, y, W - 2 * MARGIN - 120, GOLD); y -= 22
    tracked(c, "SIGHTINGS LOG", 0, y, DISP, 12, ACCENT, 2.0, center_w=W); y -= 8
    c.setFont(BODY_IT, 9.5); c.setFillColor(INK_LIGHT)
    c.drawCentredString(W / 2, y - 8, "Date · Place · What you saw"); y -= 30
    c.setStrokeColor(GOLD); c.setLineWidth(0.5)
    while y > 120:
        c.line(MARGIN, y, W - MARGIN, y); y -= 26
    footer(c, page_no, col["title"]); c.showPage()


def history_page(c, col, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "ORIGINS & HISTORY", MARGIN, y, W - 2 * MARGIN); y -= 26
    c.setFont(DISP, 22); c.setFillColor(INK); c.drawCentredString(W / 2, y, "How the legends took shape"); y -= 28
    y = dropcap(c, col.get("context") or col.get("intro", ""), MARGIN + 10, y, W - 2 * MARGIN - 20, BODY, 11, 17, INK) - 20
    icon(c, "paw", MARGIN, y - 5, 20, ACCENT_W)
    tracked(c, "SIMILAR CREATURES", MARGIN + 30, y, DISP, 11, ACCENT, 1.8); y -= 20
    y = para(c, "Black dogs shade into a wider family of spectral hounds and guardian beasts — the barghest "
                "of the north, the Manx moddey dhoo, the Welsh gwyllgi, the church grim set to guard "
                "consecrated ground, and the Cù Sìth of the Highlands. Most share the same core: a great "
                "black dog, burning eyes, and an errand between this world and the next.",
             MARGIN + 30, y, W - 2 * MARGIN - 40, BODY, 10, 15, INK_LIGHT)
    footer(c, page_no, col["title"]); c.showPage()


def checklist_page(c, col, members, page_no):
    page_bg(c); page_frame(c, GOLD, inset=30)
    y = H - MARGIN - 20
    eyebrow(c, "EXPLORER'S CHECKLIST", MARGIN, y, W - 2 * MARGIN); y -= 26
    c.setFont(DISP, 22); c.setFillColor(INK)
    c.drawCentredString(W / 2, y, "Track your discoveries"); y -= 18
    c.setFont(BODY_IT, 9.5); c.setFillColor(INK_LIGHT)
    c.drawCentredString(W / 2, y, "Tick off each legend as you track it down."); y -= 24
    colw = (W - 2 * MARGIN) / 2; half = (len(members) + 1) // 2
    for idx, m in enumerate(members):
        ci = 0 if idx < half else 1; row = idx if idx < half else idx - half
        cx = MARGIN + ci * colw; ry = y - row * 22
        c.setStrokeColor(ACCENT); c.setLineWidth(1); c.rect(cx, ry - 8, 11, 11, stroke=1, fill=0)
        c.setFont(BODY_SB, 10.5); c.setFillColor(INK); c.drawString(cx + 20, ry, m["name"])
        rx = cx + 20 + pdfmetrics.stringWidth(m["name"], BODY_SB, 10.5) + 8
        avail = (cx + colw - 16) - rx; reg = short_region(m.get("region", ""))
        c.setFont(BODY_IT, 8.5); c.setFillColor(INK_LIGHT)
        while reg and pdfmetrics.stringWidth(reg, BODY_IT, 8.5) > avail:
            reg = reg[:-1]
        if avail > 26 and reg:
            c.drawString(rx, ry, reg)
    footer(c, page_no, col["title"]); c.showPage()


def series_page(c):
    page_bg(c, dark=True); page_frame(c, GOLD, inset=26)
    gm = ROOT / "green-man.png"
    if gm.exists():
        c.drawImage(str(gm), W / 2 - 26, H - 150, 52, 52, mask="auto")
    tracked(c, "ABOUT THE SERIES", 0, H - 190, DISP, 14, GOLD, 2.6, center_w=W)
    dbl_rule(c, W / 2 - 60, H - 208, 120, GOLD)
    para(c, "The Folklore Finder Field Guide Series explores the creatures, places and people of British "
            "and Irish folklore — one theme at a time. Each guide is a companion to the interactive atlas "
            "at folklorefinder.uk. Collect them all and build your own folklore library.",
         MARGIN + 60, H - 250, W - 2 * MARGIN - 120, BODY, 12, 19, Color(0.90, 0.84, 0.70), "center")
    wax_seal(c, W / 2, H / 2 - 30, 26, "compass")
    c.setFont(BODY_IT, 10); c.setFillColor(Color(0.75, 0.66, 0.5))
    c.drawCentredString(W / 2, 150, "This is a draft example product. Content and design may change.")
    tracked(c, "FOLKLORE FINDER", 0, 112, DISP, 12, CREAM, 3.0, center_w=W)
    c.setFont(BODY_IT, 10); c.setFillColor(GOLD); c.drawCentredString(W / 2, 94, "folklorefinder.uk")
    c.showPage()


def main(slug):
    register_fonts(); ensure_assets()
    col, members = load(slug)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    map_png = FG / ("dist-%s.png" % slug)
    if not map_png.exists():
        build_distribution_map([(m["lat"], m["lng"]) for m in members if m.get("lat") is not None], map_png)
    sample = members[:4]
    suffix = os.environ.get("FIELD_GUIDE_OUTPUT_SUFFIX", "draft")
    out = OUT_DIR / ("folklore-finder-%s-field-guide-%s.pdf" % (slug, suffix))
    c = canvas.Canvas(str(out), pagesize=A4, pageCompression=1)
    c.setTitle("%s — Folklore Finder Field Guide" % col["title"]); c.setAuthor("Folklore Finder")
    p = 1
    cover(c, col, members); p += 1
    about(c, col, members, p); p += 1
    map_page(c, col, members, map_png, p); p += 1
    signs_page(c, col, p); p += 1
    for m in sample:
        profile(c, m, col["title"], p); p += 1
    places_page(c, col, members, p); p += 1
    field_page(c, col, p); p += 1
    history_page(c, col, p); p += 1
    checklist_page(c, col, members, p); p += 1
    series_page(c)
    c.save()
    print("wrote", out, "(%d pages)" % p)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "black-dogs")
