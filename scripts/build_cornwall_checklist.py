from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "folklore-finder-cornwall-explorer-checklist-draft.pdf"

PARCHMENT = HexColor("#f6f1e6")
AGED = HexColor("#efe4cf")
BURNT = HexColor("#c4622a")
GOLD = HexColor("#b09060")
OAK = HexColor("#5a4632")
SAGE = HexColor("#66735a")
SLATE = HexColor("#53667a")
INK = HexColor("#3f3023")

CATEGORY_LABELS = {
    "beast": "Beasts and strange creatures",
    "fairy": "Fae and spirits",
    "ghost": "Ghosts and restless souls",
    "giant": "Giants",
    "hero": "Legendary figures",
    "location": "Ancient and storied places",
    "pirate": "Pirates and smugglers",
    "water": "Waters and coastal lore",
    "witch": "Witches and magic",
}

FEATURED = [
    "Piskie",
    "Beast of Bodmin",
    "Tintagel Castle",
    "The Merry Maidens",
    "Dozmary Pool",
    "Cormoran, the Giant of St Michael's Mount",
    "Owlman of Mawnan",
    "Tamsin Blight",
]


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Georgia", r"C:\Windows\Fonts\georgia.ttf"))
    pdfmetrics.registerFont(TTFont("Georgia-Bold", r"C:\Windows\Fonts\georgiab.ttf"))
    pdfmetrics.registerFont(TTFont("Georgia-Italic", r"C:\Windows\Fonts\georgiai.ttf"))


def cornwall_entries() -> list[dict]:
    data = json.loads((ROOT / "legends.json").read_text(encoding="utf-8"))
    entries = [
        row
        for row in data["legends"]
        if "cornwall" in f"{row.get('region', '')} {row.get('name', '')}".lower()
        and row.get("name") != "Pixie"
    ]
    return sorted(entries, key=lambda row: row["name"].casefold())


def fit_image(c: canvas.Canvas, path: Path, x: float, y: float, w: float, h: float) -> None:
    image = ImageReader(str(path))
    iw, ih = image.getSize()
    scale = max(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    c.saveState()
    clip = c.beginPath()
    clip.rect(x, y, w, h)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(image, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, mask="auto")
    c.restoreState()


def checkbox(c: canvas.Canvas, x: float, y: float, size: float = 8) -> None:
    c.setLineWidth(0.65)
    c.setStrokeColor(GOLD)
    c.rect(x, y - size + 2, size, size, stroke=1, fill=0)


def page_base(c: canvas.Canvas, page_number: int) -> None:
    width, height = A4
    c.setFillColor(PARCHMENT)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setStrokeColor(Color(176 / 255, 144 / 255, 96 / 255, alpha=0.45))
    c.setLineWidth(0.7)
    c.rect(24, 24, width - 48, height - 48, stroke=1, fill=0)
    c.setLineWidth(0.3)
    c.rect(29, 29, width - 58, height - 58, stroke=1, fill=0)

    c.setFont("Georgia", 7.5)
    c.setFillColor(SLATE)
    c.drawString(36, 14, "FOLKLORE FINDER  |  EXPLORER'S GUILD PREVIEW")
    c.drawRightString(width - 36, 14, f"DRAFT EDITION  |  {page_number}")


def first_page(c: canvas.Canvas, entries: list[dict]) -> None:
    width, height = A4
    page_base(c, 1)

    c.setFont("Georgia", 8)
    c.setFillColor(SAGE)
    c.drawString(42, height - 58, "A PRINTABLE FIELD COMPANION")

    c.setFont("Georgia", 31)
    c.setFillColor(INK)
    c.drawString(42, height - 99, "Cornwall Folklore")
    c.setFont("Georgia", 23)
    c.setFillColor(BURNT)
    c.drawString(42, height - 132, "Explorer Checklist")

    c.setFont("Georgia-Italic", 10.5)
    c.setFillColor(OAK)
    c.drawString(43, height - 154, f"{len(entries)} stories, stones, spirits and strange places")

    hero_y = height - 352
    fit_image(c, ROOT / "legend-images" / "tintagel-hero.jpg", 42, hero_y, width - 84, 176)
    c.saveState()
    c.setFillColor(Color(25 / 255, 16 / 255, 10 / 255, alpha=0.38))
    c.rect(42, hero_y, width - 84, 176, stroke=0, fill=1)
    c.restoreState()
    c.setFillColor(PARCHMENT)
    c.setFont("Georgia-Bold", 15)
    c.drawString(58, hero_y + 29, "Begin with eight Cornish encounters")
    c.setFont("Georgia", 8.5)
    c.drawString(59, hero_y + 14, "Read the tale, find it on the map, or make the journey yourself.")

    entry_by_name = {entry["name"]: entry for entry in entries}
    start_y = hero_y - 38
    col_width = (width - 102) / 2
    for index, name in enumerate(FEATURED):
        entry = entry_by_name.get(name)
        if not entry:
            continue
        col = index % 2
        row = index // 2
        x = 48 + col * (col_width + 22)
        y = start_y - row * 53
        checkbox(c, x, y + 3, 9)
        c.setFont("Georgia-Bold", 9.2)
        c.setFillColor(INK)
        c.drawString(x + 16, y, entry["name"])
        c.setFont("Georgia-Italic", 7.4)
        c.setFillColor(SLATE)
        region = entry.get("region", "Cornwall")
        if len(region) > 43:
            region = region[:40] + "..."
        c.drawString(x + 16, y - 13, region)
        c.setStrokeColor(Color(90 / 255, 70 / 255, 50 / 255, alpha=0.16))
        c.line(x, y - 27, x + col_width, y - 27)

    note_y = 78
    c.setFillColor(AGED)
    c.roundRect(42, note_y, width - 84, 66, 3, stroke=0, fill=1)
    c.setFont("Georgia-Bold", 9)
    c.setFillColor(OAK)
    c.drawString(55, note_y + 45, "A small experiment")
    c.setFont("Georgia", 8.2)
    c.drawString(55, note_y + 29, "This draft tests whether a printable companion adds something useful to the archive.")
    c.drawString(55, note_y + 15, "The finished edition could include routes, notes, achievements and seasonal challenges.")


def draw_group(c: canvas.Canvas, x: float, y: float, width: float, label: str, rows: list[dict]) -> float:
    c.setFillColor(SAGE)
    c.setFont("Georgia-Bold", 8.3)
    c.drawString(x, y, label.upper())
    c.setStrokeColor(Color(102 / 255, 115 / 255, 90 / 255, alpha=0.35))
    c.line(x, y - 5, x + width, y - 5)
    y -= 19
    for row in rows:
        checkbox(c, x, y + 2, 7)
        name = row["name"]
        font_size = 7.7
        available = width - 13
        while font_size > 6.2 and pdfmetrics.stringWidth(name, "Georgia", font_size) > available:
            font_size -= 0.2
        c.setFont("Georgia", font_size)
        c.setFillColor(INK)
        c.drawString(x + 13, y, name)
        y -= 13.4
    return y - 10


def second_page(c: canvas.Canvas, entries: list[dict]) -> None:
    width, height = A4
    page_base(c, 2)

    c.setFont("Georgia", 8)
    c.setFillColor(SAGE)
    c.drawString(42, height - 58, "THE COMPLETE CORNWALL LIST")
    c.setFont("Georgia", 25)
    c.setFillColor(INK)
    c.drawString(42, height - 93, "Stories to seek out")
    c.setFont("Georgia-Italic", 9)
    c.setFillColor(OAK)
    c.drawString(43, height - 113, "Tick a story when you have read it, visited its place, or followed it onto the map.")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry.get("category", "other")].append(entry)

    columns = [[], []]
    heights = [0, 0]
    for category, rows in sorted(grouped.items(), key=lambda item: CATEGORY_LABELS.get(item[0], item[0])):
        estimated = 32 + len(rows) * 13.4
        target = 0 if heights[0] <= heights[1] else 1
        columns[target].append((category, rows))
        heights[target] += estimated

    col_width = (width - 106) / 2
    for col, groups in enumerate(columns):
        x = 42 + col * (col_width + 22)
        y = height - 146
        for category, rows in groups:
            y = draw_group(c, x, y, col_width, CATEGORY_LABELS.get(category, category), rows)

    notes_y = 62
    c.setStrokeColor(Color(176 / 255, 144 / 255, 96 / 255, alpha=0.35))
    c.line(42, notes_y + 45, width - 42, notes_y + 45)
    c.setFont("Georgia-Bold", 8)
    c.setFillColor(SAGE)
    c.drawString(42, notes_y + 30, "FIELD NOTES")
    c.setStrokeColor(Color(90 / 255, 70 / 255, 50 / 255, alpha=0.2))
    c.line(42, notes_y + 16, width - 42, notes_y + 16)
    c.line(42, notes_y + 2, width - 42, notes_y + 2)


def build() -> None:
    register_fonts()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    entries = cornwall_entries()
    c = canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1)
    c.setTitle("Cornwall Folklore Explorer Checklist - Draft")
    c.setAuthor("Folklore Finder")
    first_page(c, entries)
    c.showPage()
    second_page(c, entries)
    c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
