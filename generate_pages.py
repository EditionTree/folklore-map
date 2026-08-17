# -*- coding: utf-8 -*-
"""
generate_pages.py — emit static, SEO-indexable HTML pages, one per legend,
plus an A-Z index page and a full sitemap.xml.

These pages are served by Cloudflare Pages independently of the main map app.
A visitor only ever loads one of them at a time (arriving from search or a
shared link); the interactive map (map.html) is unaffected.

Run after legends.json changes:  python generate_pages.py
"""
import json, io, os, re, unicodedata, html, urllib.parse, datetime, math, hashlib, glob
from string import Template

BASE = "https://folklorefinder.uk"
OUT_DIR = "legends"
# Tracks each legend's content fingerprint + last-changed date so date_modified
# only advances when the published content actually changes (not every rebuild,
# and not from git commit timestamps). Committed to the repo.
CONTENT_STATE_FILE = "content_state.json"

# Thematic tag vocabulary (5 facets). Any tag NOT in here is treated as a
# region tag (nation / county), which is weighted lower for "relatedness".
THEMATIC_TAGS = {
    # creature/form
    "dog", "horse", "cattle", "serpent", "fish", "bird", "hare", "cat",
    "wolf", "shapeshifter", "headless", "spectral",
    # colour
    "black", "white", "green", "red", "grey", "golden",
    # setting
    "lake", "river", "sea", "coast", "well", "spring", "waterfall", "cave",
    "hill", "mountain", "forest", "bog", "moor", "island", "standing-stones",
    "barrow", "castle", "church", "bridge", "road",
    # motif/theme
    "death-omen", "curse", "treasure", "transformation", "healing",
    "prophecy", "drowning", "abduction", "battle", "revenge", "love",
    "trickery", "sacrifice", "fertility", "guardian", "haunting",
    "vanishing", "hill-figure",
    # tradition
    "celtic", "norse", "arthurian",
    # category-shaped tags that aren't place names — excluded so they don't
    # generate fake "region" pages (e.g. legends/region/fairy.html)
    "fairy", "hero", "giant", "origin", "border",
}


def content_fingerprint(leg):
    """Stable hash of the fields that make up a legend's published content."""
    parts = [
        leg.get("name", ""), leg.get("category", ""), leg.get("region", ""),
        leg.get("summary", ""), leg.get("detail") or "", leg.get("source", ""),
        repr(leg.get("lat")), repr(leg.get("lng")),
        ",".join(sorted(leg.get("tags") or [])),
    ]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def build_webp_heroes(quality=80):
    """Generate a WebP sibling for every legend hero JPG.

    Runs on every build, so newly-added *-hero.jpg files are converted
    automatically — no separate step to remember. Skips webp that are already
    up to date (webp newer than its jpg). No-op if Pillow isn't installed, in
    which case pages fall back to serving the JPG (the <source> is only emitted
    when the webp exists)."""
    try:
        from PIL import Image
    except Exception:
        print("  [webp] Pillow not installed — skipping hero WebP generation")
        return 0
    made = 0
    for jpg in glob.glob(os.path.join("legend-images", "*-hero.jpg")):
        webp = jpg[:-4] + ".webp"
        if os.path.isfile(webp) and os.path.getmtime(webp) >= os.path.getmtime(jpg):
            continue
        try:
            with Image.open(jpg) as im:
                im.convert("RGB").save(webp, "WEBP", quality=quality, method=6)
            made += 1
        except Exception as e:
            print(f"  [webp] failed {os.path.basename(jpg)}: {e}")
    if made:
        print(f"  [webp] generated/updated {made} hero WebP files")
    return made


def build_card_thumbs(width=800, quality=75):
    """Generate a small *-card.webp sibling for every legend hero JPG.

    Related-legend cards use a hero as a `cover` background in a ~469x190 box
    (3-up in the 1440px .shell), so shipping the full 1600px hero costs ~3x more
    than it can show — and there are 3 cards on every legend page. The card image
    also sits under a heavy dark gradient, which hides compression artefacts, so
    these can be encoded far harder than a hero (measured >42dB PSNR as rendered).

    Same contract as build_webp_heroes: runs every build, skips up-to-date files,
    no-op without Pillow (callers only reference the thumb when it exists)."""
    try:
        from PIL import Image
    except Exception:
        print("  [card] Pillow not installed — skipping card thumbnail generation")
        return 0
    made = 0
    for jpg in glob.glob(os.path.join("legend-images", "*-hero.jpg")):
        thumb = jpg[:-4] + "-card.webp"
        if os.path.isfile(thumb) and os.path.getmtime(thumb) >= os.path.getmtime(jpg):
            continue
        try:
            with Image.open(jpg) as im:
                w, h = im.size
                if w > width:
                    im = im.resize((width, round(h * width / w)), Image.LANCZOS)
                im.convert("RGB").save(thumb, "WEBP", quality=quality, method=6)
            made += 1
        except Exception as e:
            print(f"  [card] failed {os.path.basename(jpg)}: {e}")
    if made:
        print(f"  [card] generated/updated {made} related-card thumbnails")
    return made


def resolve_modified_dates(legends, today):
    """Set each legend's date_modified from whether its content changed since the
    last build, using a persisted fingerprint state. The date only moves when the
    content genuinely changes — so the sitemap lastmod and "Updated" labels stay
    honest. New entries baseline to date_added rather than today."""
    try:
        state = json.load(io.open(CONTENT_STATE_FILE, encoding="utf-8"))
    except Exception:
        state = {}
    new_state = {}
    for leg in legends:
        name = leg["name"]
        fp = content_fingerprint(leg)
        added = leg.get("date_added")
        prev = state.get(name)
        if prev is None:
            modified = added or today
        elif prev.get("hash") == fp:
            modified = prev.get("modified") or added or today
        else:
            modified = today
        leg["date_modified"] = modified
        new_state[name] = {"hash": fp, "modified": modified}
    with io.open(CONTENT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=0, sort_keys=True)


def human_date(iso):
    """'2026-06-12' -> '12 June 2026' (cross-platform, no %-d)."""
    try:
        dt = datetime.datetime.strptime(iso, "%Y-%m-%d")
        return f"{dt.day} {dt.strftime('%B %Y')}"
    except Exception:
        return iso or ""


def haversine_km(lat1, lng1, lat2, lng2):
    try:
        la1, lo1, la2, lo2 = map(math.radians, [lat1, lng1, lat2, lng2])
    except (TypeError, ValueError):
        return 9999.0
    dla, dlo = la2 - la1, lo2 - lo1
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def compute_related(legends, limit=10):
    """Return {name: [related legend dicts]} by tag similarity + proximity."""
    # Pre-split each legend's tags into thematic vs region sets.
    info = []
    for l in legends:
        tags = set(l.get("tags") or [])
        info.append({
            "leg": l,
            "thematic": tags & THEMATIC_TAGS,
            "region": tags - THEMATIC_TAGS,
            "lat": l.get("lat"), "lng": l.get("lng"),
        })
    related = {}
    for i, a in enumerate(info):
        scored = []
        for j, b in enumerate(info):
            if i == j:
                continue
            shared_theme = len(a["thematic"] & b["thematic"])
            shared_region = len(a["region"] & b["region"])
            dist = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
            if dist < 25:
                prox = 3
            elif dist < 75:
                prox = 2
            elif dist < 160:
                prox = 1
            else:
                prox = 0
            score = 3 * shared_theme + shared_region + prox
            if score <= 0:
                continue
            scored.append((score, -dist, b["leg"]))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        related[a["leg"]["name"]] = [t[2] for t in scored[:limit]]
    return related


def compute_nearby(legends, limit=4, max_km=200):
    """Return {name: [(legend, distance_km), ...]} of the geographically closest
    entries — pure haversine distance, distinct from the tag-weighted related list.
    Entries beyond max_km are dropped so remote legends don't list false neighbours."""
    pts = [(l, l.get("lat"), l.get("lng")) for l in legends]
    nearby = {}
    for leg, la, lo in pts:
        if la is None or lo is None:
            nearby[leg["name"]] = []
            continue
        dists = []
        for other, ola, olo in pts:
            if other is leg or ola is None or olo is None:
                continue
            d = haversine_km(la, lo, ola, olo)
            if d <= max_km:
                dists.append((d, other))
        dists.sort(key=lambda t: t[0])
        nearby[leg["name"]] = [(other, d) for d, other in dists[:limit]]
    return nearby


# ── Browse-by-category / browse-by-region support ──────────────────────────
NATIONS = ["england", "scotland", "wales", "ireland", "northern-ireland", "isle-of-man", "channel-islands"]

# <title> for the 7 nation region pages leads with the adjective form
# ("English Folklore") to match real search phrasing — see
# project_seo_keyword_research memory. County/area pages keep the
# "Folklore of X" fallback below; only these 7 get the override.
NATION_TITLES = {
    "england": "English Folklore — Myths & Legends",
    "scotland": "Scottish Folklore — Myths & Legends",
    "wales": "Welsh Folklore — Myths & Legends",
    "ireland": "Irish Folklore — Myths & Legends",
    "northern-ireland": "Northern Irish Folklore — Myths & Legends",
    "isle-of-man": "Manx Folklore — Myths & Legends",
    "channel-islands": "Channel Islands Folklore — Myths & Legends",
}

# <title> for the 11 category browse pages — leads with a natural search
# phrase instead of the generic "{label} of Britain & Ireland" pattern.
# See project_seo_keyword_research memory.
CATEGORY_TITLES = {
    "beast": "British Monsters & Mythical Beasts — Folklore Map",
    "deity": "British & Irish Deities — Folklore Map",
    "dragon": "British Dragon Legends — Folklore Map",
    "fairy": "British & Irish Fairies — Folklore Map",
    "ghost": "British Ghost Stories — Folklore Map",
    "giant": "British Giant Legends — Folklore Map",
    "hero": "British Legendary Heroes — Folklore Map",
    "location": "British Sacred Sites — Folklore Map",
    "pirate": "British Pirates & Smugglers — Folklore Map",
    "water": "British Water Monsters & Mermaids — Folklore Map",
    "witch": "British Witches & Witch Trials — Folklore Map",
}

# Themed collections: a page is only generated when at least this many entries
# qualify, so curated collections never ship as thin pages.
MIN_COLLECTION = 12
# Entries per collection page; larger collections paginate (page 1 = /<slug>,
# page n = /<slug>-n).
COLLECTION_PER_PAGE = 24


def collection_page_url(slug, page):
    """URL for a collection page (page 1 has no suffix)."""
    suffix = "" if page == 1 else f"-{page}"
    return f"{BASE}/{OUT_DIR}/collection/{slug}{suffix}"


def period_page_url(slug):
    return f"{BASE}/{OUT_DIR}/period/{slug}"


def pagination_html(slug, page, total_pages):
    """Numbered Prev/Next pagination for a paginated collection."""
    if total_pages <= 1:
        return ""
    def cell(label, target, current=False, disabled=False):
        if current:
            return f'<span class="current" aria-current="page">{label}</span>'
        if disabled:
            return f'<span class="disabled">{label}</span>'
        return f'<a href="{collection_page_url(slug, target)}">{label}</a>'
    parts = ['<nav class="pagination" aria-label="Collection pages">']
    parts.append(cell("&#8249; Prev", page - 1, disabled=(page == 1)))
    for p in range(1, total_pages + 1):
        # Always show first, last, and a window around the current page.
        if p == 1 or p == total_pages or abs(p - page) <= 1:
            parts.append(cell(str(p), p, current=(p == page)))
        elif p == 2 and page > 3:
            parts.append('<span class="gap">&#8230;</span>')
        elif p == total_pages - 1 and page < total_pages - 2:
            parts.append('<span class="gap">&#8230;</span>')
    parts.append(cell("Next &#8250;", page + 1, disabled=(page == total_pages)))
    parts.append('</nav>')
    return "".join(parts)


def load_collections():
    """Load curated themed-collection definitions; empty list if absent."""
    try:
        return json.load(io.open("collections.json", encoding="utf-8")).get("collections", [])
    except Exception:
        return []


def load_periods():
    """Load the canonical historical-period list (Explore Through Time);
    empty list if absent — in chronological order as authored."""
    try:
        return json.load(io.open("periods.json", encoding="utf-8")).get("periods", [])
    except Exception:
        return []


def load_sightings():
    """Load curated 'recent sightings' news entries per legend, keyed by legend
    name; {} if absent. Each entry: date, title, source_name, url, confidence
    ('reported' for mainstream coverage, 'possible' for lower-confidence
    hobbyist/tracker sources). This is hand-curated (backfilled, then reviewed
    monthly), never auto-published — see content-style-guide.md."""
    try:
        return json.load(io.open("sightings.json", encoding="utf-8"))
    except Exception:
        return {}


def load_page_intros():
    """Curated category/region intros; {} if absent. Missing keys fall back to
    the generator's auto one-liner, so this can be filled in over time."""
    try:
        d = json.load(io.open("page_intros.json", encoding="utf-8"))
        return d.get("categories", {}), d.get("regions", {})
    except Exception:
        return {}, {}


def load_featured_pages():
    """Legend pages that have completed artwork and editorial metadata.

    Keeping this in a manifest lets the redesign roll out gradually without
    changing image-less pages or hand-editing generated HTML.
    """
    try:
        return json.load(io.open("legend_pages.json", encoding="utf-8")).get("pages", {})
    except Exception:
        return {}


def _simple_match(leg, cond):
    """A single condition: tags_all / tags_any / categories, all ANDed."""
    tags = set(leg.get("tags") or [])
    if "tags_all" in cond and not set(cond["tags_all"]) <= tags:
        return False
    if "tags_any" in cond and not (set(cond["tags_any"]) & tags):
        return False
    if "categories" in cond and leg.get("category") not in cond["categories"]:
        return False
    return True


def matches_collection(leg, match):
    """Evaluate a collection `match`: an `any`/`all` list of conditions, or a
    single simple condition."""
    if "any" in match:
        return any(_simple_match(leg, c) for c in match["any"])
    if "all" in match:
        return all(_simple_match(leg, c) for c in match["all"])
    return _simple_match(leg, match)


def prettify_region(tag):
    special = {"isle-of-man": "Isle of Man", "channel-islands": "Channel Islands"}
    if tag in special:
        return special[tag]
    if tag.startswith("county-"):
        return "County " + tag[7:].replace("-", " ").title()
    return tag.replace("-", " ").title()


def banner_html():
    return ""


# Site-wide top navigation. The interactive map mirrors these values in its
# embedded CSS because it has a map-specific header control group.
TOPNAV_CSS = (
    # Canonical banner: Home footer brown, gilded top piping + bottom
    # divider, brand lockup (emblem + "Folklore Finder") anchored left, and
    # the centered nav links. Mirrors the .topnav rules in folklorefinder.css.
    ".topnav{position:relative;display:flex;align-items:center;justify-content:center;"
    "flex-wrap:wrap;gap:4px;min-height:58px;padding:10px clamp(16px,3vw,52px);"
    "background:#1a0e06;border-bottom:none}"
    ".topnav::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;"
    "background:linear-gradient(90deg,transparent 0%,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent 100%)}"
    ".topnav::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;"
    "background:linear-gradient(90deg,transparent 0%,rgba(176,144,96,0.6) 20%,rgba(196,98,42,0.8) 50%,rgba(176,144,96,0.6) 80%,transparent 100%)}"
    ".topnav a{font-family:'Marcellus',serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;"
    "color:rgba(242,232,213,0.78);text-decoration:none;padding:6px 14px;border-radius:3px;"
    "transition:background .15s,color .15s}"
    ".topnav a:hover{color:#f2e8d5;background:rgba(196,98,42,0.18)}"
    ".topnav a.active{color:#c4622a}"
    # Lucide icon + label per link. Scoped to .topnav-links so it can't catch
    # the brand lockup, which is also a .topnav a.
    ".topnav-links a{display:inline-flex;align-items:center;gap:6px}"
    ".topnav-links a svg{flex:0 0 auto}"
    ".topnav-brand{position:absolute;left:clamp(14px,3vw,52px);top:50%;transform:translateY(-50%);"
    "display:inline-flex;align-items:center;gap:11px;text-decoration:none}"
    # padding:0 has to outrank `.topnav a{padding:6px 14px}`, which is the more
    # specific selector — as `.topnav-brand{padding:0}` it never applied, and
    # the lockup silently carried 28px it was never meant to have. That padding
    # was what pushed the iconned link row into the lockup at ~1200px.
    ".topnav a.topnav-brand{padding:0}"
    ".topnav a.topnav-brand:hover{background:transparent}"
    ".topnav-emblem{width:40px;height:40px;object-fit:contain;display:block;flex-shrink:0;"
    "transition:opacity .15s,transform .15s}"
    ".topnav-brand:hover .topnav-emblem{opacity:.85;transform:scale(1.04)}"
    ".topnav-title{font-family:'Marcellus',serif;font-size:clamp(18px,2.1vw,23px);font-weight:400;"
    "text-transform:none;letter-spacing:0.055em;color:#f2e8d5;white-space:nowrap;"
    "text-shadow:0 1px 3px rgba(0,0,0,0.55),0 0 14px rgba(196,98,42,0.22)}"
    "@media(max-width:1200px){.topnav-brand{display:none}}"
    # Links get their own flex track so the search can pin right without
    # joining them, and so the mobile scroll below moves the links alone.
    ".topnav-links{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;"
    "gap:4px;flex:1 1 auto;min-width:0}"
    # Mobile: one horizontally scrolling row instead of wrapped nav links.
    "@media(max-width:640px){.topnav{flex-wrap:nowrap;justify-content:flex-start;"
    "padding-left:12px;padding-right:12px}"
    ".topnav-links{flex-wrap:nowrap;justify-content:flex-start;overflow-x:auto;"
    "overflow-y:hidden;scrollbar-width:none}"
    ".topnav-links::-webkit-scrollbar{display:none}"
    ".topnav a{flex:0 0 auto;padding:9px 11px;font-size:11px;white-space:nowrap}}"
    # Persistent nav search — pinned right (mirroring .topnav-brand's
    # absolute-left lockup) so the links stay centred in the full bar.
    # Square edges, antique-gold rule and the gilded-piping stripe on the
    # dropdown, matching the site's other editorial furniture. Below 1150px
    # it collapses to an icon opening a panel under the bar. See nav-search.js.
    # (1150px: links are centred in the full bar, so the room to their
    # right shrinks by ~half of any viewport shrink.)
    ".nav-search{position:absolute;right:clamp(14px,3vw,52px);top:50%;"
    "transform:translateY(-50%);display:flex;align-items:center;width:220px}"
    ".nav-search-toggle{display:none;align-items:center;justify-content:center;width:34px;"
    "height:34px;padding:0;background:transparent;border:1px solid rgba(176,144,96,.4);"
    "border-radius:0;color:rgba(242,232,213,.8);font-size:15px;line-height:1;cursor:pointer;"
    "transition:border-color .15s,color .15s,background .15s}"
    ".nav-search-toggle:hover,.nav-search-toggle:focus-visible{border-color:#c4622a;"
    "background:rgba(196,98,42,.18);color:#f2e8d5;outline:none}"
    ".nav-search-drop{position:relative;width:100%}"
    ".nav-search-field{display:flex;align-items:center;gap:8px;width:100%;padding:7px 11px;"
    "background:rgba(242,232,213,.07);border:1px solid rgba(176,144,96,.4);border-radius:0;"
    "transition:background .15s,border-color .15s}"
    ".nav-search-field:focus-within{background:rgba(242,232,213,.13);"
    "border-color:#c4622a}"
    ".nav-search-icon{flex:0 0 auto;color:#b09060}"
    ".nav-search-input{flex:1;min-width:0;background:none;border:0;outline:none;color:#f2e8d5;"
    "font-family:'Spectral',serif;font-size:13px}"
    ".nav-search-input::placeholder{color:rgba(242,232,213,.42);font-style:italic}"
    ".nav-search-results{position:absolute;top:calc(100% + 9px);right:0;"
    "width:min(330px,calc(100vw - 24px));max-height:370px;overflow-y:auto;display:none;"
    "z-index:30;text-align:left;background:#241a10;border:1px solid rgba(176,144,96,.4);"
    "border-radius:0;box-shadow:0 14px 34px rgba(0,0,0,.45)}"
    ".nav-search-results::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;"
    "background:linear-gradient(90deg,transparent 0%,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent 100%)}"
    ".nav-search-results.open{display:block}"
    ".nav-search-item{display:block;padding:10px 14px;cursor:pointer;"
    "border-top:1px solid rgba(176,144,96,.16)}"
    ".nav-search-item:first-child{border-top:0}"
    ".nav-search-item:hover,.nav-search-item.active{background:rgba(196,98,42,.18)}"
    ".nsi-name{display:block;font-family:'Marcellus',serif;font-size:13.5px;color:#f2e8d5}"
    ".nsi-meta{display:block;margin-top:2px;font-family:'Spectral',serif;font-style:italic;"
    "font-size:11.5px;color:rgba(242,232,213,.55)}"
    ".nav-search-empty{padding:15px 14px;font-family:'Spectral',serif;font-style:italic;"
    "font-size:12.5px;color:rgba(242,232,213,.55)}"
    "@media(max-width:1149px){"
    ".nav-search,.nav-search:focus-within{position:static;transform:none;flex:0 0 auto;"
    "margin-left:14px;width:auto}"
    ".nav-search-toggle{display:inline-flex}"
    ".nav-search-drop{display:none;position:absolute;top:calc(100% + 10px);"
    "right:clamp(12px,3vw,52px);width:min(330px,calc(100vw - 24px));z-index:30}"
    ".nav-search.open .nav-search-drop{display:block}"
    ".nav-search-field{padding:10px 13px}"
    ".nav-search-field{background:#241a10;border-color:rgba(176,144,96,.5);"
    "box-shadow:0 14px 34px rgba(0,0,0,.45)}"
    ".nav-search-results{width:100%}}"
    "footer{position:relative;text-align:center;padding:12px 18px;font-size:12px;line-height:1.6;"
    "color:rgba(246,241,230,.78);background:#1a0e06;border-top:0}"
    "footer::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;"
    "background:linear-gradient(90deg,transparent 0%,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent 100%)}"
    "footer a{color:rgba(246,241,230,.9);text-decoration:none}"
    "footer a:hover{color:#f2e8d5}"
    # Lucide icon inside a footer link (the Ko-fi cup) — aligned off the
    # baseline, as the footer is inline text rather than a flex row.
    "footer a svg{vertical-align:-.15em;margin-right:5px}"
)

# Lucide line icons (lucide.dev, ISC), inlined rather than linked: they inherit
# currentColor from whatever they sit in and cost no extra request. Size is
# carried on the element so an icon renders correctly with no CSS at all. The
# bodies below are each icon's own geometry, copied unaltered from
# lucide-static 1.31.0 — don't hand-tune them, re-copy from lucide.dev instead.
LUCIDE_BODIES = {
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.34-4.34"/>',
    "map": '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
    "map-pin": '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
    "compass": '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/>',
    "library": '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
    "scroll-text": '<path d="M15 12h-5"/><path d="M15 8h-5"/><path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"/>',
    "hourglass": '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
    "book-open": '<path d="M12 5v16"/><path d="M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z"/>',
    "eye": '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    "coffee": '<path d="M10 2v2"/><path d="M14 2v2"/><path d="M16 8a1 1 0 0 1 1 1v8a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1h14a4 4 0 1 1 0 8h-1"/><path d="M6 2v2"/>',
    "house": '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "list": '<path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"/><path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"/><path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17"/>',
    "bookmark": '<path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "share-2": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
}


def lucide(name, size, cls=""):
    """One inline Lucide icon. `cls` is an optional class attribute value."""
    return (
        '<svg%s width="%d" height="%d" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">%s</svg>'
        % (' class="%s"' % cls if cls else "", size, size, LUCIDE_BODIES[name])
    )


def side_head(kicker, heading, icon):
    """A sidebar card's kicker + icon-led heading."""
    return (
        '<p class="side-kicker">%s</p>'
        '<h2>%s%s</h2>' % (kicker, lucide(icon, 19, "side-icon"), heading)
    )


FOOTER_HTML = (
    '<footer>Folklore Finder &nbsp;&#183;&nbsp; '
    'An atlas of myths, legends, &amp; stories &nbsp;&#183;&nbsp; '
    '&#169; EditionTree &nbsp;&#183;&nbsp; '
    '<a href="https://folklorefinder.uk/about">About</a> &nbsp;&#183;&nbsp; '
    '<a href="https://folklorefinder.uk/updates">Updates</a> &nbsp;&#183;&nbsp; '
    '<a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener">'
    + lucide("coffee", 13) + 'Ko-fi</a> &nbsp;&#183;&nbsp; '
    '<a href="https://folklorefinder.uk/privacy">Privacy</a></footer>'
)

# key, label, path, Lucide icon. Distinct icons throughout: "map" doubles with
# the homepage's Explore-the-map button because it is the same destination, but
# nothing else reuses a glyph the legend sidebar already spends.
TOPNAV_ITEMS = [
    ("home", "Home", "/", "house"),
    ("map", "Map", "/map", "map"),
    ("browse", "Browse", "/" + OUT_DIR + "/", "list"),
    ("collections", "Collections", "/" + OUT_DIR + "/collections", "layers"),
    ("archive", "My Archive", "/archive", "bookmark"),
    ("about", "About", "/about", "info"),
]


NAV_SEARCH_HTML = (
    '<div class="nav-search" id="navSearch">'
    '<button type="button" class="nav-search-toggle" id="navSearchToggle" '
    'aria-label="Search legends" aria-expanded="false" aria-controls="navSearchDrop">'
    + lucide("search", 15) +
    '</button>'
    '<div class="nav-search-drop" id="navSearchDrop">'
    '<div class="nav-search-field">'
    + lucide("search", 14, "nav-search-icon") +
    '<input type="text" id="navSearchInput" class="nav-search-input" placeholder="Search legends…" '
    'autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" '
    'aria-controls="navSearchResults" aria-autocomplete="list" aria-label="Search legends"/>'
    '</div>'
    '<div class="nav-search-results" id="navSearchResults" role="listbox" aria-label="Search results"></div>'
    '</div>'
    '</div>'
)


def topnav_html(active=""):
    parts = ['<nav class="topnav">']
    parts.append(
        f'<a class="topnav-brand" href="{BASE}/" aria-label="Folklore Finder home">'
        f'<img class="topnav-emblem" src="{BASE}/green-man.png" alt="Green Man"/>'
        f'<span class="topnav-title">Folklore Finder</span></a>'
    )
    parts.append('<div class="topnav-links">')
    for key, label, path, ic in TOPNAV_ITEMS:
        cls = ' class="active"' if key == active else ''
        parts.append(
            f'<a href="{BASE}{path}"{cls}>{lucide(ic, 13)}'
            f'<span>{label}</span></a>'
        )
    parts.append('</div>')
    parts.append(NAV_SEARCH_HTML)
    parts.append('</nav>')
    parts.append('<script src="/nav-search.js?v=20260817b" defer></script>')
    return "".join(parts)


def footer_html():
    return FOOTER_HTML


def nav_links(items, active):
    """items: list of (url, label, key)."""
    parts = ['<nav class="browse-nav">']
    for url, label, key in items:
        cls = ' class="active"' if key == active else ''
        parts.append('<a href="' + url + '"' + cls + '>' + esc(label) + '</a>')
    parts.append('</nav>')
    return ''.join(parts)


def browse_card(leg, slugmap, cats, meta, show_cat, show_summary=False):
    cat = leg.get("category", "")
    href = BASE + "/" + OUT_DIR + "/" + slugmap[leg["name"]]
    chip = ""
    if show_cat:
        colour = meta.get(cat, {}).get("colour", "#8b3a1a")
        chip = ('<span class="b-cat" style="background:' + esc(colour) + '">'
                + esc(cats.get(cat, cat)) + '</span>')
    summary = ""
    if show_summary and leg.get("summary"):
        summary = '<span class="b-summary">' + esc(leg["summary"]) + '</span>'
    return ('<a class="b-card" href="' + href + '">' + chip
            + '<span class="b-name">' + esc(leg["name"]) + '</span>'
            + '<span class="b-region">' + esc(leg.get("region", "")) + '</span>'
            + summary + '</a>')


def collection_article_html(members, slugmap, cats, meta, featured_pages):
    """Alternating image/summary rows for a collection's members — an editorial
    'article' layout (image left/right on alternating rows) instead of a card grid."""
    rows = []
    for l in members:
        name = l["name"]
        href = BASE + "/" + OUT_DIR + "/" + slugmap[name]
        cat = l.get("category", "")
        colour = meta.get(cat, {}).get("colour", "#8b3a1a")
        catname = cats.get(cat, cat)
        img = featured_pages.get(name, {}).get("image", "")
        summary = short_desc(l.get("summary", ""), 260)
        media = ""
        if img:
            media = ('<div class="col-article-media">'
                     f'<img src="{BASE}/{img.replace(os.sep, "/")}" alt="{esc(name)}" loading="lazy"/></div>')
        region = (f'<span class="col-article-region">{esc(l.get("region", ""))}</span>'
                  if l.get("region") else "")
        rows.append(
            '<a class="col-article" href="' + href + '">' + media
            + '<div class="col-article-body">'
            + f'<span class="col-article-cat" style="background:{esc(colour)}">{esc(catname)}</span>'
            + f'<h3 class="col-article-name">{esc(name)}</h3>' + region
            + f'<p class="col-article-summary">{esc(summary)}</p>'
            + '<span class="col-article-more">Read the legend &#8594;</span>'
            + '</div></a>'
        )
    return "\n".join(rows)


BROWSE_STYLE = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(circle at 12% 8%,rgba(176,144,96,.1),transparent 25rem),linear-gradient(180deg,#e8dcc5,#f6f1e6 34rem,#eadfc9);color:#3f3023;font-family:'Spectral',serif;line-height:1.7;min-height:100vh}
/* Mobile safeguard: keep the page itself from scrolling sideways. */
@media(max-width:900px){html,body{overflow-x:hidden}}
.site-banner{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#1a0e06 0%,#2c1510 55%,#3d1e0c 100%);padding:16px 20px;text-align:center}
.site-banner::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}
.site-banner::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}
.banner-link{display:inline-flex;align-items:center;gap:13px;text-decoration:none}
.banner-emblem{width:48px;height:48px;object-fit:contain;flex-shrink:0}
.banner-text{display:flex;flex-direction:column;align-items:center;line-height:1.15}
.banner-title{font-family:'Marcellus',serif;font-size:21px;font-weight:400;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}
.banner-title i{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}
.banner-sub{font-family:'Spectral',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}
@media(max-width:560px){.banner-title{font-size:15px}.banner-emblem{width:38px;height:38px}.banner-sub{font-size:11px}}
.wrap{width:min(1440px,calc(100% - 56px));max-width:none;margin:0 auto;padding:34px 0 68px}
.crumb{font-size:12px;color:#5c4a2a;margin-bottom:14px}
.crumb a{color:#8b3a1a;text-decoration:none}
.browse-h1{font-family:'Marcellus',serif;font-size:clamp(32px,4vw,48px);margin-bottom:6px;color:#3f3023;line-height:1.12;font-weight:400}
.browse-h1::after{content:"";display:block;width:132px;height:40px;margin:9px 0 5px;background:url('/assets/ornaments/generated-variants/oak-divider-horizontal.webp') left center/contain no-repeat;opacity:.55}
.browse-intro{max-width:780px;font-size:17px;color:#5c4a2a;margin-bottom:20px;line-height:1.6}
.browse-nav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.browse-nav a{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#9d461f;border:1px solid rgba(90,70,50,.35);border-radius:0;padding:5px 11px;text-decoration:none}
.browse-nav a:hover,.browse-nav a.active{background:#5a4632;color:#f6f1e6;border-color:#5a4632}
.browse-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:15px}
.b-card{position:relative;background:rgba(246,241,230,.74);border:1px solid rgba(90,70,50,.3);border-radius:0;padding:16px 17px;text-decoration:none;color:#3f3023;box-shadow:inset 0 0 0 5px rgba(255,255,255,.15);transition:border-color .15s,transform .1s,background .15s}
.b-card:hover{border-color:#c4622a;transform:translateY(-2px)}
.b-card span{display:block}
.b-cat{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#9d461f;padding:2px 8px;border-radius:0;margin-bottom:8px;width:max-content;max-width:100%}
.b-name{font-family:'Marcellus',serif;font-size:15px;line-height:1.25;margin-bottom:4px}
.b-region{font-style:italic;font-size:12px;color:#5c4a2a}
.b-summary{font-size:13.5px;color:#3a2c14;margin-top:8px;line-height:1.5}
.back{display:inline-block;margin-top:24px;font-size:13px;color:#5c4a2a}
.pagination{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:7px;margin-top:30px}
.pagination a,.pagination span{font-family:'Marcellus',serif;font-size:13px;min-width:34px;text-align:center;padding:6px 10px;border:1px solid #b09060;border-radius:0;text-decoration:none;color:#9d461f}
.pagination a:hover{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}
.pagination .current{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}
.pagination .disabled{color:#b09060;border-color:#d8c8a8;cursor:default}
.pagination .gap{border:none;color:#5c4a2a;min-width:auto;padding:6px 2px}
@media(max-width:900px){.wrap{width:calc(100% - 32px)}}
@media(max-width:620px){.browse-grid{grid-template-columns:1fr}}
/* Collection hero: description on the left, iconic image on the right */
.col-hero-split{display:flex;gap:30px;align-items:stretch;margin:14px 0 24px}
.col-hero-desc{flex:1 1 0;min-width:0;display:flex;flex-direction:column;justify-content:center}
.col-hero-desc p{font-size:17px;color:#5c4a2a;line-height:1.62;max-width:58ch}
/* The context paragraph now sits inside the text column under the lede — keep
   its smaller size (.col-hero-desc p would otherwise win on specificity) and
   drop the 820px cap, since the column already constrains it. */
.col-hero-desc .col-context{font-size:15.5px;max-width:none;margin:12px 0 0}
.col-hero-media{flex:0 0 42%;position:relative;min-height:320px;aspect-ratio:4/3;overflow:visible;box-shadow:0 6px 24px rgba(0,0,0,.25);background:#241a10}
.col-hero-media img{position:absolute;inset:0;width:100%;height:100%;border-radius:2px;object-fit:cover;object-position:center top}
/* Same oak-branch leaf frame as the homepage's weekly-legend image
   (.home-page .hero-feature .lotw-hero::after in folklorefinder.css) —
   reused here so the collection hero reads as the same kind of "featured
   artwork," not a plain photo. */
.col-hero-media::after{content:'';position:absolute;inset:-17px;z-index:2;box-sizing:border-box;border:36px solid transparent;border-image:url('/assets/ornaments/generated-variants/oak-branch-frame-v1.png?v=20260713c') 230 / 35px / 0 round;filter:saturate(.62) brightness(.88) contrast(.9) drop-shadow(0 4px 5px rgba(0,0,0,.24));pointer-events:none}
.col-hero-credit{position:absolute;right:24px;bottom:24px;z-index:3;font-size:10px;color:rgba(255,255,255,.85);background:rgba(0,0,0,.4);padding:2px 8px;border-radius:2px}
@media(max-width:680px){.col-hero-split{flex-direction:column;gap:16px}.col-hero-media{flex-basis:auto;height:220px;min-height:0}.col-hero-media::after{inset:-12px;border-width:24px;border-image-width:24px}}
/* Article layout: alternating image/summary rows for collection members */
.col-articles{display:flex;flex-direction:column;gap:20px}
.col-article{display:flex;align-items:stretch;background:rgba(246,241,230,.72);border:1px solid rgba(90,70,50,.28);text-decoration:none;color:#3f3023;overflow:hidden;box-shadow:inset 0 0 0 5px rgba(255,255,255,.14);transition:border-color .15s,transform .12s,box-shadow .15s}
.col-article:hover{border-color:#c4622a;transform:translateY(-2px);box-shadow:0 10px 26px rgba(44,31,14,.14),inset 0 0 0 5px rgba(255,255,255,.14)}
.col-article:nth-child(even){flex-direction:row-reverse}
.col-article-media{flex:0 0 42%;position:relative;aspect-ratio:16/9;background:#241a10}
.col-article-media img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.col-article-body{flex:1 1 0;min-width:0;padding:16px 26px;display:flex;flex-direction:column;justify-content:center}
.col-article-cat{align-self:flex-start;font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#9d461f;padding:2px 9px;margin-bottom:9px}
.col-article-name{font-family:'Marcellus',serif;font-weight:400;font-size:22px;line-height:1.15;color:#3f3023;margin-bottom:3px}
.col-article-region{font-style:italic;font-size:12.5px;color:#5c4a2a}
.col-article-summary{font-size:14.5px;color:#3a2c14;line-height:1.6;margin:10px 0 12px}
.col-article-more{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#9d461f}
.col-article:hover .col-article-more{color:#c4622a}
@media(max-width:680px){.col-article,.col-article:nth-child(even){flex-direction:column}.col-article-media{flex-basis:auto;min-height:0}.col-article-body{padding:18px 20px}.col-article-name{font-size:19px}}
/* Collections index: editorial feature rows (alternating image/text) */
.col-index{display:flex;flex-direction:column;gap:22px}
.col-index-row{position:relative;display:flex;align-items:stretch;background:rgba(228,213,185,.88);border:1px solid rgba(90,70,50,.28);text-decoration:none;color:#3f3023;overflow:hidden;box-shadow:inset 0 0 0 5px rgba(255,255,255,.14);transition:border-color .15s,transform .12s,box-shadow .15s}
.col-index-row:hover{border-color:#c4622a;transform:translateY(-2px);box-shadow:0 12px 30px rgba(44,31,14,.16),inset 0 0 0 5px rgba(255,255,255,.14)}
.col-index-row:nth-child(even){flex-direction:row-reverse}
/* Gilded piping — same transparent/rust/gold/rust/transparent stripe as
   .topnav::before, the footer rule and the share cards — as a top accent
   so these list-view cards read as a deliberate site motif, not a plain box. */
.col-index-row::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;z-index:2;background:linear-gradient(90deg,transparent 0%,#c4622a 15%,#b09060 50%,#c4622a 85%,transparent 100%)}
.col-index-media{flex:0 0 42%;position:relative;min-height:320px;background:#241a10}
.col-index-media img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center top}
.col-index-body{flex:1 1 0;min-width:0;padding:28px 34px;display:flex;flex-direction:column;justify-content:center}
.col-index-count{align-self:flex-start;font-family:'Marcellus',serif;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#9d461f;margin-bottom:10px}
.col-index-name{font-family:'Marcellus',serif;font-weight:400;font-size:clamp(24px,2.5vw,32px);line-height:1.12;color:#3f3023;margin-bottom:10px}
.col-index-intro{font-size:15px;color:#3a2c14;line-height:1.62;margin-bottom:14px}
.col-index-more{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9d461f}
.col-index-row:hover .col-index-more{color:#c4622a}
/* Per-visitor collection progress — populated client-side from localStorage,
   hidden by default so nothing flashes before JS resolves it. */
.col-index-progress,.col-progress{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:2px 0 12px}
.col-index-progress[hidden],.col-progress[hidden]{display:none}
.cip-bar{position:relative;flex:0 1 120px;height:4px;border-radius:2px;background:rgba(90,70,50,.18);overflow:hidden}
.cip-fill{position:absolute;inset:0;width:0%;background:#9d461f;border-radius:2px;transition:width .3s}
.cip-label{font-size:11px;color:#5c4a2a;white-space:nowrap}
.col-index-row.done{border-color:#c4622a}
.col-index-row.done .cip-label{color:#9d461f}
.col-progress .cip-bar{flex:0 1 200px}
.col-share-btn{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#c4622a;background:transparent;border:1px solid #b09060;border-radius:3px;padding:5px 12px;cursor:pointer;transition:border-color .15s,color .15s;margin-left:8px}
.col-share-btn:hover,.col-share-btn:focus-visible{border-color:#c4622a;color:#9d461f}
.col-share-btn[disabled]{opacity:.6;cursor:default}
.col-share-status{font-size:11px;color:#5c4a2a}
@media(max-width:680px){.col-index-row,.col-index-row:nth-child(even){flex-direction:column}.col-index-media{flex-basis:auto;height:212px;min-height:0}.col-index-body{padding:20px 22px}}
.col-section{margin-top:38px}
.col-section h2{font-family:'Marcellus',serif;font-size:20px;font-weight:400;color:#3f3023;margin-bottom:12px}
.col-context{font-size:15.5px;color:#3f3023;max-width:820px;line-height:1.7;margin:0 0 14px}
.col-maplink{margin:2px 0 26px}
.col-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.col-gallery img{width:100%;height:110px;object-fit:cover;border-radius:2px;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.col-related{display:flex;flex-wrap:wrap;gap:8px}
.col-related a{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#9d461f;border:1px solid rgba(90,70,50,.35);border-radius:0;padding:6px 12px;text-decoration:none}
.col-related a:hover{background:#5a4632;color:#f6f1e6;border-color:#5a4632}
.col-resources{list-style:none}
.col-resources li+li{margin-top:6px}
.col-resources a{color:#8b3a1a;font-size:14px}
.wrap.ornamented{position:relative}
.wrap.ornamented::before{
  content:"";position:absolute;top:-10px;right:-18px;width:150px;height:150px;
  opacity:.1;pointer-events:none;z-index:0;
  background:url('/assets/ornaments/generated-variants/oak-corner-upper-right.webp') right top/contain no-repeat;
}
.wrap.ornamented > *{position:relative;z-index:1}
"""


def track_event_script(event_type, **fields):
    """Fire-and-forget analytics beacon for a static page (collection/period
    views) — mirrors legend-page.js's trackEvent() but standalone since these
    pages don't load that shared script."""
    payload = json.dumps({"event_type": event_type, **fields}, ensure_ascii=False)
    return (
        "<script>(function(){try{"
        "var s=sessionStorage.getItem('ff_session_id');"
        "if(!s){s=Math.random().toString(36).slice(2)+Date.now().toString(36);sessionStorage.setItem('ff_session_id',s);}"
        "var p=Object.assign({referring_page:location.pathname,session_id:s}," + payload + ");"
        "fetch('https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-event',"
        "{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p),keepalive:true}).catch(function(){});"
        "}catch(e){}})();</script>\n"
    )


def collection_index_progress_script():
    """Populates the begin/continue/complete state on each collection card on
    the collections landing page, from the same ff_visited_legends_v1
    localStorage key My Archive reads. One small JSON fetch per card
    (collection/<slug>.json, already generated for the map's collection
    filter), so cost stays proportional to the number of collections shown."""
    return (
        "<script>(function(){try{"
        "var visited=JSON.parse(localStorage.getItem('ff_visited_legends_v1')||'null')||{};"
        "var set=new Set(Object.keys(visited));"
        "document.querySelectorAll('.col-index-row[data-slug]').forEach(function(row){"
        "var slug=row.getAttribute('data-slug');"
        "fetch('collection/'+slug+'.json').then(function(r){return r.json();}).then(function(d){"
        "var members=d.legends||[];"
        "if(!members.length)return;"
        "var count=members.filter(function(n){return set.has(n);}).length;"
        "var pct=Math.round(count/members.length*100);"
        "var done=count===members.length;"
        "var prog=row.querySelector('.col-index-progress');"
        "var more=row.querySelector('.col-index-more');"
        "if(prog){"
        "prog.hidden=false;"
        "prog.querySelector('.cip-fill').style.width=pct+'%';"
        "prog.querySelector('.cip-label').textContent=done?'Collection complete \\u2713':(count+' of '+members.length+' discovered');"
        "}"
        "if(more)more.textContent=done?'Revisit the collection \\u2192':(count>0?'Continue collection \\u2192':'Begin collection \\u2192');"
        "if(done)row.classList.add('done');"
        "}).catch(function(){});"
        "});"
        "}catch(e){}})();</script>\n"
    )


def collection_detail_progress_script(slug, title):
    """Same progress computation as collection_index_progress_script(), but
    for the single collection page itself — one summary bar near the top
    rather than one per card. Fetches its own membership JSON relative to
    the page (same directory), since the full member list isn't known
    client-side otherwise (pages 2+ only carry that page's slice).

    Also reveals the "Share this collection" button (only present in the
    page-1 markup, since it needs the .col-hero-media photo that only page 1
    renders) once the collection is complete, and wires it to the shared
    /share-card.js renderer — same template as the achievement-unlock and
    nearest-legend cards, with the collection's own hero photo as a circular
    medallion instead of a wax seal."""
    share_title = f"{title} — complete!"
    share_text = f'I completed the "{title}" collection on Folklore Finder!'
    filename_prefix = f"folklore-finder-{slug}-collection"
    return (
        # Loaded first (and left as a normal blocking <script src>, not
        # defer/async) so it's guaranteed to have executed — and
        # window.ShareCard to exist — before the inline script below runs.
        '<script src="/share-card.js"></script>\n'
        "<script>(function(){try{"
        "var visited=JSON.parse(localStorage.getItem('ff_visited_legends_v1')||'null')||{};"
        "var set=new Set(Object.keys(visited));"
        "fetch('" + slug + ".json').then(function(r){return r.json();}).then(function(d){"
        "var members=d.legends||[];"
        "if(!members.length)return;"
        "var count=members.filter(function(n){return set.has(n);}).length;"
        "var pct=Math.round(count/members.length*100);"
        "var done=count===members.length;"
        "var el=document.querySelector('.col-progress');"
        "if(!el)return;"
        "el.hidden=false;"
        "el.classList.toggle('done',done);"
        "el.querySelector('.cip-fill').style.width=pct+'%';"
        "el.querySelector('.cip-label').textContent=done?'Collection complete \\u2713':(count+' of '+members.length+' discovered');"
        "var shareBtn=el.querySelector('.col-share-btn');"
        "var heroImg=document.querySelector('.col-hero-media img');"
        "if(!shareBtn||!done||!heroImg||!window.ShareCard)return;"
        "shareBtn.hidden=false;"
        "shareBtn.addEventListener('click',function(){"
        "var statusEl=el.querySelector('.col-share-status');"
        "var idle=shareBtn.textContent;"
        "shareBtn.disabled=true;shareBtn.textContent='Generating\\u2026';"
        "if(statusEl)statusEl.textContent='';"
        "window.ShareCard.renderPhotoCard({"
        "kicker:'COLLECTION COMPLETE',"
        "subKicker:members.length+' legends discovered',"
        "title:" + json.dumps(title, ensure_ascii=False) + ","
        "body:'Every legend in this collection, found.',"
        "photoSrc:heroImg.currentSrc||heroImg.src"
        "}).then(function(blob){"
        "return window.ShareCard.shareOrDownload(blob," + json.dumps(filename_prefix + ".png", ensure_ascii=False) + ","
        + json.dumps(share_title, ensure_ascii=False) + "," + json.dumps(share_text, ensure_ascii=False) + ");"
        "}).then(function(outcome){"
        "if(statusEl)statusEl.textContent=outcome==='shared'?'Shared!':(outcome==='downloaded'?'Image saved':'');"
        "}).catch(function(){"
        "if(statusEl)statusEl.textContent=\"Couldn't generate the image \\u2014 try again.\";"
        "}).then(function(){shareBtn.disabled=false;shareBtn.textContent=idle;});"
        "});"
        "}).catch(function(){});"
        "}catch(e){}})();</script>\n"
    )


def build_browse_page(page_title, desc, url, h1, intro, crumb, nav_html, cards_html,
                      ogimage=None, jsonld=None, head_extra="", after_grid="", nav_active="browse",
                      hero_html="", extra_sections="", after_intro="", wrap_class="", track_script="",
                      top_nav_html="", grid_class="browse-grid"):
    jsonld_html = ('<script type="application/ld+json">' + jsonld + '</script>\n') if jsonld else ''
    page_breadcrumb = breadcrumb_list([
        ("Home", BASE + "/"),
        ("All legends", f"{BASE}/{OUT_DIR}/"),
        (crumb, url),
    ])
    breadcrumb_jsonld_html = (
        '<script type="application/ld+json">' +
        json.dumps(page_breadcrumb, ensure_ascii=False) +
        '</script>\n'
    )
    return ('<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8"/>\n'
            '<script>if(location.hostname.indexOf("pages.dev")>-1){location.replace("https://folklorefinder.uk"+location.pathname+location.search+location.hash);}</script>\n'
            '<script defer src=\'https://static.cloudflareinsights.com/beacon.min.js\' data-cf-beacon=\'{"token": "64d1fd37251d426f8a0d8fbc83ea350b"}\'></script>\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
            '<title>' + esc(page_title) + '</title>\n'
            '<meta name="description" content="' + esc(desc) + '"/>\n'
            '<link rel="canonical" href="' + url + '"/>\n'
            '<link rel="icon" type="image/png" href="' + BASE + '/favicon.png"/>\n'
            '<meta property="og:type" content="website"/>\n'
            '<meta property="og:title" content="' + esc(h1) + '"/>\n'
            '<meta property="og:description" content="' + esc(desc) + '"/>\n'
            '<meta property="og:url" content="' + url + '"/>\n'
            '<meta property="og:image" content="' + (ogimage or (BASE + '/og/preview.jpg')) + '"/>\n'
            '<meta property="og:site_name" content="Folklore Finder"/>\n'
            '<meta name="twitter:card" content="summary_large_image"/>\n'
            '<meta name="twitter:title" content="' + esc(h1) + '"/>\n'
            '<meta name="twitter:description" content="' + esc(desc) + '"/>\n'
            '<meta name="twitter:image" content="' + (ogimage or (BASE + '/og/preview.jpg')) + '"/>\n'
            '\n'
            '<link rel="stylesheet" href="/fonts/fonts.css"/>\n'
            + jsonld_html + breadcrumb_jsonld_html + head_extra
            + '<style>' + BROWSE_STYLE + TOPNAV_CSS + '</style></head>\n<body class="catalogue-page">\n'
            + topnav_html(nav_active) + '\n<main id="main-content" tabindex="-1">\n' + banner_html() + '\n<div class="wrap' + (' ' + wrap_class if wrap_class else '') + '">\n'
            '<nav class="crumb"><a href="' + BASE + '/">Home</a> &#8250; '
            '<a href="' + BASE + '/' + OUT_DIR + '/">All legends</a> &#8250; '
            '<span>' + esc(crumb) + '</span></nav>\n'
            '<h1 class="browse-h1">' + esc(h1) + '</h1>\n'
            + top_nav_html
            + hero_html
            + (('<p class="browse-intro">' + esc(intro) + '</p>\n') if intro else '')
            + after_intro
            + nav_html + '\n<div class="' + grid_class + '">\n' + cards_html
            + '\n</div>\n' + after_grid + extra_sections
            + '<a class="back" href="' + BASE + '/' + OUT_DIR + '/">&#8592; Browse All Legends</a>\n'
            '</div>\n</main>\n' + footer_html() + '\n' + track_script + '</body></html>')


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "legend"


def esc(s):
    return html.escape(s or "", quote=True)


def inline_text(s):
    """Collapse source newlines and stray spacing for one HTML text run."""
    return re.sub(r"\s+", " ", s or "").strip()


def short_desc(summary, limit=155):
    s = re.sub(r"\s+", " ", summary or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0] + "…"


def absolute_asset_url(path):
    """Convert a repo-relative asset path to the canonical public URL."""
    return f"{BASE}/{(path or '').replace(os.sep, '/')}".rstrip("/")


def image_object(path, name, caption="", width=None, height=None):
    """Schema.org ImageObject for crawlable generated artwork."""
    if not path:
        return None
    obj = {
        "@type": "ImageObject",
        "url": absolute_asset_url(path),
        "contentUrl": absolute_asset_url(path),
        "name": name,
    }
    if caption:
        obj["caption"] = caption
        obj["description"] = caption
    if width:
        obj["width"] = width
    if height:
        obj["height"] = height
    return obj


def breadcrumb_list(items):
    """Schema.org BreadcrumbList from [(label, url), ...]."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": label, "item": url}
            for i, (label, url) in enumerate(items)
        ],
    }


def host_of(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "") or "source"
    except Exception:
        return "source"


TITLE_SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into",
    "nor", "of", "on", "or", "over", "per", "the", "to", "up", "via", "with",
}


def title_word(word, force=False):
    """Editorial title case for generated headings without flattening names."""
    if not word:
        return word
    if not force and word.lower() in TITLE_SMALL_WORDS:
        return word.lower()
    if any(ch.isupper() for ch in word[1:]) or word.isupper():
        return word
    return word[:1].upper() + word[1:]


def title_case_text(text):
    """Capitalise headings while leaving small joining words lower-case."""
    if not isinstance(text, str):
        return text
    text = inline_text(text)
    if not text:
        return text
    parts = re.split(r"(\s+)", text)
    word_indexes = [i for i, p in enumerate(parts) if p and not p.isspace()]
    if not word_indexes:
        return text
    first, last = word_indexes[0], word_indexes[-1]
    out = []
    for i, part in enumerate(parts):
        if i not in word_indexes:
            out.append(part)
            continue
        bits = re.split(r"([-–—/])", part)
        cased = []
        for j, bit in enumerate(bits):
            if bit in {"-", "–", "—", "/"}:
                cased.append(bit)
                continue
            force = i == first or i == last or (j > 0 and bits[j - 1] in {"-", "–", "—", "/"})
            cased.append(title_word(bit, force=force))
        out.append("".join(cased))
    return "".join(out)


# Human-readable publisher names for the sources we cite. Unmapped hosts fall
# back to the bare hostname, so this only needs the common/known ones.
PUBLISHERS = {
    "en.wikipedia.org": "Wikipedia",
    "historic-uk.com": "Historic UK",
    "gutenberg.org": "Project Gutenberg",
    "mysteriousbritain.co.uk": "Mysterious Britain & Ireland",
    "atlasobscura.com": "Atlas Obscura",
    "nationaltrust.org.uk": "National Trust",
    "transceltic.com": "Transceltic",
    "greatbritishlife.co.uk": "Great British Life",
    "duchas.ie": "Dúchas (National Folklore Collection of Ireland)",
    "jerseyheritage.org": "Jersey Heritage",
    "folklorethursday.com": "Folklore Thursday",
    "visitwales.com": "Visit Wales",
    "oxfordreference.com": "Oxford Reference",
    "irishcentral.com": "IrishCentral",
    "historicengland.org.uk": "Historic England",
    "canmore.org.uk": "Canmore",
    "lincolnshirefolktalesproject.com": "Lincolnshire Folk Tales Project",
    "archive.org": "Internet Archive",
    "celt.ucc.ie": "CELT: Corpus of Electronic Texts",
    "iso.ucc.ie": "Irish Sagas Online",
    "sacred-texts.com": "Internet Sacred Text Archive",
    "en.wikisource.org": "Wikisource",
    "english-heritage.org.uk": "English Heritage",
    "heritageireland.ie": "Heritage Ireland",
    "library.wales": "National Library of Wales",
    "witches.hca.ed.ac.uk": "Survey of Scottish Witchcraft",
    "britannica.com": "Encyclopaedia Britannica",
    "isle-of-man.com": "A Manx Notebook",
    "undiscoveredscotland.co.uk": "Undiscovered Scotland",
    "britishfairies.wordpress.com": "British Fairies",
    "spookyisles.com": "Spooky Isles",
    "icysedgwick.com": "Icy Sedgwick",
    "coflein.gov.uk": "Coflein (RCAHMW)",
    "historicenvironment.scot": "Historic Environment Scotland",
    "cadw.gov.wales": "Cadw",
    "cudl.lib.cam.ac.uk": "Cambridge Digital Library",
    "isos.dias.ie": "Irish Script on Screen",
    "quod.lib.umich.edu": "University of Michigan Digital Collections",
    "libraryireland.com": "Library Ireland",
    "british-history.ac.uk": "British History Online",
    "babel.hathitrust.org": "HathiTrust",
    "catalog.hathitrust.org": "HathiTrust",
    "openlibrary.org": "Open Library",
    "books.google.com": "Google Books",
    "d.lib.rochester.edu": "University of Rochester (Robbins Library)",
    "dib.ie": "Dictionary of Irish Biography",
    "worldhistory.org": "World History Encyclopedia",
    "encyclopedia.com": "Encyclopedia.com",
    "cambridge.org": "Cambridge University Press",
    "tandfonline.com": "Taylor & Francis",
    "jstor.org": "JSTOR",
    "historyireland.com": "History Ireland",
    "academia.edu": "Academia.edu",
    "codecs.vanhamel.nl": "CODECS (van Hamel Foundation)",
    "manxnationalheritage.im": "Manx National Heritage",
    "peoplescollection.wales": "People’s Collection Wales",
    "heritagegateway.org.uk": "Heritage Gateway",
    "ancientmonuments.uk": "Ancient Monuments",
    "paranormaldatabase.com": "The Paranormal Database",
    "voicesfromthedawn.com": "Voices from the Dawn",
    "themodernantiquarian.com": "The Modern Antiquarian",
    "thenorthernantiquarian.org": "The Northern Antiquarian",
    "legendarydartmoor.co.uk": "Legendary Dartmoor",
    "mythicalireland.com": "Mythical Ireland",
    "electricscotland.com": "Electric Scotland",
    "genuki.org.uk": "GENUKI",
    "spookyscotland.net": "Spooky Scotland",
    "scotlands-stories.com": "Scotland’s Stories",
    "oldechronicles.org.uk": "Olde Chronicles",
    "belfastentries.com": "Belfast Entries",
    "faeryfolklorist.blogspot.com": "The Faery Folklorist",
    "britainexpress.com": "Britain Express",
    "lincolnshirelife.co.uk": "Lincolnshire Life",
    "cornwalls.co.uk": "Cornwalls.co.uk",
    "carrowkeel.com": "Carrowkeel",
    "shetland.org": "Shetland.org",
    "rte.ie": "RTÉ",
    "orcadian.co.uk": "The Orcadian",
    "tradfolk.co": "Tradfolk",
    "historyhit.com": "HistoryHit",
    "countrylife.co.uk": "Country Life",
    # News outlets and periodicals. These read as sloppy when shown as a bare
    # domain, and the mapping is unambiguous, so they are worth naming even
    # though each is only cited a handful of times.
    "irishnews.com": "The Irish News",
    "derryjournal.com": "Derry Journal",
    "irishexaminer.com": "Irish Examiner",
    "scotsman.com": "The Scotsman",
    "newsletter.co.uk": "The News Letter",
    "westmeathindependent.ie": "Westmeath Independent",
    "eadt.co.uk": "East Anglian Daily Times",
    "grimsbytelegraph.co.uk": "Grimsby Telegraph",
    "greatyarmouthmercury.co.uk": "Great Yarmouth Mercury",
    "stratford-herald.com": "Stratford Herald",
    "feeds.bbci.co.uk": "BBC News",
    "bbc.co.uk": "BBC",
    "history.co.uk": "HISTORY UK",
    "moonmausoleum.com": "Moon Mausoleum",
    "nation.cymru": "Nation.Cymru",
    "irishheritagenews.ie": "Irish Heritage News",
    "hyperallergic.com": "Hyperallergic",
    "iflscience.com": "IFLScience",
    "ancient-origins.net": "Ancient Origins",
}


def publisher_of(url):
    """Friendly publisher name for a source URL, or the bare host if unmapped."""
    return PUBLISHERS.get(host_of(url), host_of(url))


# Source reliability tier by host. Only confident classifications are listed;
# unmapped hosts get no tier label (rather than a misleading guess). Entries can
# override per-source with an explicit "type" in their `sources` list.
SOURCE_TIERS = {
    "en.wikipedia.org": "encyclopedic",
    "oxfordreference.com": "encyclopedic",
    "duchas.ie": "primary",
    "gutenberg.org": "primary",
    "historicengland.org.uk": "heritage",
    "canmore.org.uk": "heritage",
    "nationaltrust.org.uk": "heritage",
    "jerseyheritage.org": "heritage",
    "calanais.org": "heritage",
    "wessexmuseums.org.uk": "heritage",
    "glencoemuseum.com": "heritage",
    # Three national institutions the 2026-08-09 expansion pass missed. The
    # other hosts cited alongside them are already classified further down.
    "library.wales": "primary",
    "english-heritage.org.uk": "heritage",
    "heritageireland.ie": "heritage",
    "folklorethursday.com": "secondary",
    "transceltic.com": "secondary",
    "mysteriousbritain.co.uk": "secondary",
    "historic-uk.com": "secondary",
    # Added 2026-08-09 — sourcing_audit.py flagged 179 hosts across 126 entries
    # as unrecognised. Classified in one pass against sourcing_audit_report.json
    # (see project_sourcing_tier_expansion memory for the full reasoning).
    # primary
    "archive.org": "primary",
    "cambridge.org": "primary",
    "en.wikisource.org": "primary",
    "jstor.org": "primary",
    "libraryireland.com": "primary",
    "sacred-texts.com": "primary",
    "tandfonline.com": "primary",
    "witches.hca.ed.ac.uk": "primary",
    # encyclopedic
    "britannica.com": "encyclopedic",
    "commons.wikimedia.org": "encyclopedic",
    "dib.ie": "encyclopedic",
    "mythopedia.com": "encyclopedic",
    "pantheon.org": "encyclopedic",
    "worldhistory.org": "encyclopedic",
    # heritage
    "askaboutireland.ie": "heritage",
    "blog.geolsoc.org.uk": "heritage",
    "blog.historicenvironment.scot": "heritage",
    "blogs.loc.gov": "heritage",
    "cadw.gov.wales": "heritage",
    "cistercianway.wales": "heritage",
    "cornwallheritagetrust.org": "heritage",
    "crowlandabbey.org.uk": "heritage",
    "discoverboynevalley.ie": "heritage",
    "essexrecordofficeblog.co.uk": "heritage",
    "fforestfawrgeopark.org.uk": "heritage",
    "geolsoc.org.uk": "heritage",
    "heritagegateway.org.uk": "heritage",
    "hhct.co.uk": "heritage",
    "kentdowns.org.uk": "heritage",
    "kilkennyheritage.ie": "heritage",
    "kilshannig.heritagecork.org": "heritage",
    "monaghan.ie": "heritage",
    "nationalchurchestrust.org": "heritage",
    "northumberlandarchives.com": "heritage",
    "nrscotland.gov.uk": "heritage",
    "orkneyheritagesociety.org.uk": "heritage",
    "parismuseescollections.paris.fr": "heritage",
    "stmelangell.org": "heritage",
    "stmichaelsmount.co.uk": "heritage",
    "sussexarch.org.uk": "heritage",
    "tireeplacenames.org": "heritage",
    "worcestercathedrallibrary.wordpress.com": "heritage",
    # secondary
    "academia.edu": "secondary",
    "allaboutdragons.com": "secondary",
    "ancient-origins.net": "secondary",
    "ancientclans.org": "secondary",
    "anglesey-history.co.uk": "secondary",
    "anomalyinfo.com": "secondary",
    "atlasobscura.com": "secondary",
    "bagtownclans.com": "secondary",
    "bardmythologies.com": "secondary",
    "belfastentries.com": "secondary",
    "blackdrago.com": "secondary",
    "blackpigsdyke.ie": "secondary",
    "brehonacademy.org": "secondary",
    "britainexpress.com": "secondary",
    "britishfolklore.com": "secondary",
    "calendarcustoms.com": "secondary",
    "catholicireland.net": "secondary",
    "connollycove.com": "secondary",
    "cornishancientsites.com": "secondary",
    "cornwall-plus.co.uk": "secondary",
    "cornwall.co.uk": "secondary",
    "cornwalls.co.uk": "secondary",
    "countrylife.co.uk": "secondary",
    "curiousireland.ie": "secondary",
    "discovernorthernireland.com": "secondary",
    "drrosarikingston.com": "secondary",
    "emeraldisle.ie": "secondary",
    "executedtoday.com": "secondary",
    "experience-enniskillen.com": "secondary",
    "feeds.bbci.co.uk": "secondary",
    "frontiersmagazine.org": "secondary",
    "goldenageofpiracy.org": "secondary",
    "greatbritishghosttour.co.uk": "secondary",
    "history.co.uk": "secondary",
    "historyhit.com": "secondary",
    "historyireland.com": "secondary",
    "hypnogoria.com": "secondary",
    "icysedgwick.com": "secondary",
    "iflscience.com": "secondary",
    "ireland.com": "secondary",
    "irishcentral.com": "secondary",
    "irishcultureandtraditions.org": "secondary",
    "irishexaminer.com": "secondary",
    "irishgodsandgoddesses.net": "secondary",
    "irishheritagenews.ie": "secondary",
    "irishlegal.com": "secondary",
    "irishmyths.com": "secondary",
    "karlshuker.blogspot.com": "secondary",
    "landoflegends.wales": "secondary",
    "lincolnshirefolktalesproject.com": "secondary",
    "lincolnshirelife.co.uk": "secondary",
    "lurganancestry.com": "secondary",
    "medievalhistory.info": "secondary",
    "mothershipton.co.uk": "secondary",
    "mythicalireland.com": "secondary",
    "mythslegendsodditiesnorth-east-wales.co.uk": "secondary",
    "nation.cymru": "secondary",
    "newsletter.co.uk": "secondary",
    "northernireland.org": "secondary",
    "oldechronicles.org.uk": "secondary",
    "orkney.com": "secondary",
    "orkneyology.com": "secondary",
    "outaboutscotland.com": "secondary",
    "paranormaldatabase.com": "secondary",
    "riverbannloughneagh.org": "secondary",
    "rootsnorthernireland.com": "secondary",
    "rte.ie": "secondary",
    "sabre-roads.org.uk": "secondary",
    "scotlands-stories.com": "secondary",
    "scotsman.com": "secondary",
    "secretireland.ie": "secondary",
    "shetland.org": "secondary",
    "sites.pitt.edu": "secondary",
    "socialhistory.org.uk": "secondary",
    "spiritedisle.ie": "secondary",
    "spookyisles.com": "secondary",
    "spookyscotland.net": "secondary",
    "storyarchaeology.com": "secondary",
    "stratford-herald.com": "secondary",
    "themodernantiquarian.com": "secondary",
    "thenorthernantiquarian.org": "secondary",
    "thirdeyetraveller.com": "secondary",
    "timelessmyths.com": "secondary",
    "tradfolk.co": "secondary",
    "undiscoveredscotland.co.uk": "secondary",
    "unexplained.ie": "secondary",
    "visitcumbria.com": "secondary",
    "visitguernsey.com": "secondary",
    "visitwales.com": "secondary",
    "voicesfromthedawn.com": "secondary",
    "w1711.org": "secondary",
    "wales.com": "secondary",
    "westmeathindependent.ie": "secondary",
    "whirlpool-scotland.co.uk": "secondary",
    "wikishire.co.uk": "secondary",
    "wookey.co.uk": "secondary",
    "yourirish.com": "secondary",
    # popular
    "altmore.com": "popular",
    "badreputation.org.uk": "popular",
    "baltimore.ie": "popular",
    "belfastchildis.com": "popular",
    "blog.mullmonastery.com": "popular",
    "bohosilver.co.uk": "popular",
    "britishfairies.wordpress.com": "popular",
    "broughshane.org.uk": "popular",
    "celticelegance.com": "popular",
    "clan.com": "popular",
    "cmrosens.com": "popular",
    "cornishbirdblog.com": "popular",
    "eelandotter.net": "popular",
    "esmeraldamac.wordpress.com": "popular",
    "faeryfolklorist.blogspot.com": "popular",
    "finn-mccool.co.uk": "popular",
    "grahamwatkins.info": "popular",
    "hillwalktours.com": "popular",
    "irishfolklore.wordpress.com": "popular",
    "loughneaghtours.com": "popular",
    "lovetovisitireland.com": "popular",
    "morbidology.com": "popular",
    "mulldirectory.co.uk": "popular",
    "mythicalireland.blogspot.com": "popular",
    "nationalpurebreddogday.com": "popular",
    "newgrange.com": "popular",
    "nightbringer.se": "popular",
    "northlinkferries.co.uk": "popular",
    "realmwhispers.com": "popular",
    "scotlandinmyheartsite.wordpress.com": "popular",
    "singinghead.wordpress.com": "popular",
    "strangeandtwisted.com": "popular",
    "tellstory.net": "popular",
    "theirishrose.com": "popular",
    "thelastleprechaunsofireland.com": "popular",
    "thetipperaryantiquarian.blogspot.com": "popular",
    "visionsofthepastblog.com": "popular",
    "visittotnes.co.uk": "popular",
    "welshgiftshop.com": "popular",
    "wildswim.ie": "popular",
    # Added 2026-08-09, second pass — a whole-dataset scan (not just the
    # worst-flagged-reason-per-entry audit) turned up more hosts that only
    # appeared as a SECONDARY source on an entry already flagged for a
    # different reason, so the first pass's audit-driven extraction missed
    # them. See project_sourcing_tier_expansion memory.
    # primary
    "babel.hathitrust.org": "primary",
    "bartleby.com": "primary",
    "bibliovault.org": "primary",
    "books.google.com": "primary",
    "british-history.ac.uk": "primary",
    "catalog.hathitrust.org": "primary",
    "ccel.org": "primary",
    "celt.ucc.ie": "primary",
    "d.lib.rochester.edu": "primary",
    "eprints.chi.ac.uk": "primary",
    "iso.ucc.ie": "primary",
    "isos.dias.ie": "primary",
    "middleenglishromance.org.uk": "primary",
    "openlibrary.org": "primary",
    "quod.lib.umich.edu": "primary",
    "sites.exeter.ac.uk": "primary",
    "sources.nli.ie": "primary",
    "taylorfrancis.com": "primary",
    "uwp.co.uk": "primary",
    # encyclopedic
    "encyclopedia.com": "encyclopedic",
    # heritage
    "ancientmonuments.uk": "heritage",
    "beacons-npa.gov.uk": "heritage",
    "breconbeacons.org": "heritage",
    "brodgar.co.uk": "heritage",
    "causewaycoastandglens.gov.uk": "heritage",
    "coflein.gov.uk": "heritage",
    "discoverulsterscots.com": "heritage",
    "eastsussex.gov.uk": "heritage",
    "gloucestershire.gov.uk": "heritage",
    "heritage-explorer.lincolnshire.gov.uk": "heritage",
    "layersoflondon.org": "heritage",
    "lincstrust.org.uk": "heritage",
    "manxnationalheritage.im": "heritage",
    "museumofwitchcraftandmagic.co.uk": "heritage",
    "museums.gov.gg": "heritage",
    "nevern-church.org.uk": "heritage",
    "niarchive.org": "heritage",
    "northlincolnshiremuseum.co.uk": "heritage",
    "ourwarwickshire.org.uk": "heritage",
    "pembrokeshirecoast.wales": "heritage",
    "peoplescollection.wales": "heritage",
    "priaulxlibrary.co.uk": "heritage",
    "rcahmw.gov.uk": "heritage",
    "rct.uk": "heritage",
    "shetlandmuseumandarchives.org.uk": "heritage",
    "southdowns.gov.uk": "heritage",
    "waterfordtreasures.com": "heritage",
    "wrothsilver.org.uk": "heritage",
    # secondary
    "abookofcreatures.com": "secondary",
    "aboutalford.com": "secondary",
    "abovedown.co.uk": "secondary",
    "anglesey-today.com": "secondary",
    "antrimhistory.net": "secondary",
    "arts.ulster.ac.uk": "secondary",
    "asmanxasthehills.com": "secondary",
    "bitesizedbritain.co.uk": "secondary",
    "buildinghistory.org": "secondary",
    "carrowkeel.com": "secondary",
    "channeleye.media": "secondary",
    "cornwallforever.co.uk": "secondary",
    "darkoxfordshire.co.uk": "secondary",
    "derryjournal.com": "secondary",
    "discoverceredigion.co.uk": "secondary",
    "discoverceredigion.wales": "secondary",
    "discoverhighlandsandislands.scot": "secondary",
    "discoverportrush.com": "secondary",
    "eadt.co.uk": "secondary",
    "eatsleepliveherefordshire.co.uk": "secondary",
    "electricscotland.com": "secondary",
    "enjoyingnorfolk.co.uk": "secondary",
    "fermanaghroots.com": "secondary",
    "findagrave.com": "secondary",
    "folklorescotland.com": "secondary",
    "genuki.org.uk": "secondary",
    "great-castles.com": "secondary",
    "greatbritishlife.co.uk": "secondary",
    "greatyarmouthmercury.co.uk": "secondary",
    "grimsbytelegraph.co.uk": "secondary",
    "guernseydonkey.com": "secondary",
    "haunted-britain.com": "secondary",
    "hauntedhistoryoflincolnshire.blogs.lincoln.ac.uk": "secondary",
    "hauntedpalaceblog.com": "secondary",
    "henhamhistory.org": "secondary",
    "hiddenscotland.co": "secondary",
    "hiddenscotland.com": "secondary",
    "historiamag.com": "secondary",
    "history.gg": "secondary",
    "historypoints.org": "secondary",
    "hyperallergic.com": "secondary",
    "insearchofholywellsandhealingsprings.wordpress.com": "secondary",
    "irishnews.com": "secondary",
    "isle-of-man.com": "secondary",
    "isleofjura.scot": "secondary",
    "jersey.com": "secondary",
    "legendarydartmoor.co.uk": "secondary",
    "lostcartography.com": "secondary",
    "matadornetwork.com": "secondary",
    "mayo-ireland.ie": "secondary",
    "medievalchronicles.com": "secondary",
    "morrigan.academy": "secondary",
    "norfolkfolkloresociety.co.uk": "secondary",
    "norwoodsociety.co.uk": "secondary",
    "occult-world.com": "secondary",
    "orcadian.co.uk": "secondary",
    "pistyllrhaeadr.co.uk": "secondary",
    "plant-lore.com": "secondary",
    "saintpatrickcentre.com": "secondary",
    "sark.co.uk": "secondary",
    "sharonhoward.org": "secondary",
    "tellinghistory.co.uk": "secondary",
    "thathistorycouple.co.uk": "secondary",
    "theantonineitineraries.blogspot.com": "secondary",
    "theblacknun.com": "secondary",
    "thelocalmythstorian.com": "secondary",
    "throughthearchives.wordpress.com": "secondary",
    "tuatha.ie": "secondary",
    "turtlebunbury.com": "secondary",
    "ucc.ie": "secondary",
    "visitarmagh.com": "secondary",
    "visitbath.co.uk": "secondary",
    "visitmidwales.co.uk": "secondary",
    "visitnorthwales.co.uk": "secondary",
    "visitstronsay.com": "secondary",
    "visitthebroads.co.uk": "secondary",
    "visitwarrenpoint.com": "secondary",
    "welsh-mythsandlegends.walesdirectory.co.uk": "secondary",
    # popular
    "arthurlamy.wordpress.com": "popular",
    "barnesandnoble.com": "popular",
    "catherinecavendish.com": "popular",
    "clydesburn.blogspot.com": "popular",
    "crypticinquiry.com": "popular",
    "eaglehill.us": "popular",
    "eastmidlandsfolklore.wordpress.com": "popular",
    "ferries.orkney.com": "popular",
    "firespringsfolktales.wordpress.com": "popular",
    "garve.org": "popular",
    "hauntedohiobooks.com": "popular",
    "ianmiddleton.co.uk": "popular",
    "internationaltimes.it": "popular",
    "islandfolktales.wordpress.com": "popular",
    "katielarmour.com": "popular",
    "kerrieanngardner.co.uk": "popular",
    "lochnessmystery.blogspot.com": "popular",
    "lovetovisitscotland.com": "popular",
    "minehead.storywalks.info": "popular",
    "moonmausoleum.com": "popular",
    "peatzeria.com": "popular",
    "shetlandwithlaurie.com": "popular",
    "sublimewales.wordpress.com": "popular",
    "technotink.net": "popular",
    "theroyalvictoria.co.uk": "popular",
    "timhodkinson.blogspot.com": "popular",
    "tracymonger.wordpress.com": "popular",
    "what-when-how.com": "popular",
    "worldwidewriter.co.uk": "popular",
}
TIER_LABELS = {
    "primary": "primary record",
    "heritage": "heritage record",
    "secondary": "secondary source",
    "encyclopedic": "encyclopedic",
    "popular": "popular source",
}


TIER_CHIPS = {
    "primary": "Primary",
    "heritage": "Heritage",
    "secondary": "Secondary",
    "encyclopedic": "Encyclopedic",
    "popular": "Popular",
}


def source_tier(url, explicit=None):
    """Reliability tier for a source, or None when not confidently known."""
    if explicit and explicit in TIER_LABELS:
        return explicit
    return SOURCE_TIERS.get(host_of(url))


def legend_sources(leg):
    """Normalise a legend's sourcing into a list of {url, publisher, tier, label}.
    Supports the new `sources` list (strings or {url,type,publisher} objects) and
    falls back to the legacy single `source` string."""
    raw = leg.get("sources")
    items = []
    if raw:
        for s in raw:
            if isinstance(s, str) and s:
                items.append({"url": s})
            elif isinstance(s, dict) and s.get("url"):
                items.append(s)
    if not items and leg.get("source"):
        items = [{"url": leg["source"]}]
    out = []
    for s in items:
        url = s["url"]
        tier = source_tier(url, s.get("type"))
        out.append({
            "url": url,
            "publisher": s.get("publisher") or publisher_of(url),
            "tier": tier,
            "label": TIER_LABELS.get(tier) if tier else None,
        })
    return out




FEATURED_PAGE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<script>if(location.hostname.indexOf("pages.dev")>-1){location.replace("https://folklorefinder.uk"+location.pathname+location.search+location.hash);}</script>
<script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{"token":"64d1fd37251d426f8a0d8fbc83ea350b"}'></script>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>$title</title>
<meta name="description" content="$desc"/>
<link rel="canonical" href="$url"/>
<link rel="icon" type="image/png" href="$base/favicon.png"/>
<meta property="og:type" content="article"/>
<meta property="og:url" content="$url"/>
<meta property="og:title" content="$ogtitle"/>
<meta property="og:description" content="$desc"/>
<meta property="og:image" content="$ogimage"/>
<meta property="og:image:width" content="$og_w"/>
<meta property="og:image:height" content="$og_h"/>
<meta property="og:image:alt" content="$og_alt"/>
<meta property="og:site_name" content="Folklore Finder"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="$ogtitle"/>
<meta name="twitter:description" content="$desc"/>
<meta name="twitter:image" content="$ogimage"/>
<meta name="twitter:image:alt" content="$og_alt"/>
<link rel="stylesheet" href="/fonts/fonts.css"/>
<link rel="stylesheet" href="/assets/leaflet/leaflet.css"/>
<link rel="stylesheet" href="/legend-page.css?v=20260817f"/>
<script type="application/ld+json">$jsonld</script>
$breadcrumb_jsonld
</head>
<body>
$topnav
<main id="main-content" tabindex="-1">
  <div class="shell">
    $breadcrumb
    <section class="hero" aria-labelledby="legend-title">
      $hero_media
      <div class="hero-copy">
        <div class="eyebrow">
          <span class="category" style="background:$catcolour">$catname</span>
          <span class="place">$region</span>
        </div>
        <h1 id="legend-title">$name</h1>
        $pronunciation
        <p class="standfirst">$standfirst</p>
      </div>
    </section>

    <div class="content-grid">
      <article class="article">
        <div class="article-label">The Legend</div>
        $featured_body
        $editorial
        <div class="article-actions" aria-label="Legend actions">
          <a class="button" href="$maplink">$icon_map<span class="btn-label">Open on Full Map</span></a>
          <button class="button secondary" id="copyLinkBtn" type="button">$icon_link<span class="btn-label">Copy link</span></button>
          <button class="button secondary" id="webShareBtn" type="button" hidden>$icon_share<span class="btn-label">Share</span></button>
        </div>
        <span class="share-status" id="shareStatus" role="status" aria-live="polite"></span>
      </article>

      <aside class="sidebar" aria-label="Legend details">
        <div class="sidebar-col">$sidebar_col1</div>
        <div class="sidebar-col">$sidebar_col2</div>
      </aside>
    </div>
  </div>

  $featured_related
</main>
$footer
<script src="/assets/leaflet/leaflet.js"></script>
<script src="/share-card.js"></script>
<script src="$base/legend-page.js?v=20260817a"></script>
</body>
</html>
""")


def load_category_meta():
    """Extract category -> {colour, iconPath} from index.html (single source of truth)."""
    try:
        text = io.open("map.html", encoding="utf-8").read()
    except Exception:
        return {}
    meta = {}
    for m in re.finditer(
        r"(\w+):\s*\{[^{}]*?colour:\s*[\"']([^\"']+)[\"'][^{}]*?iconPath:\s*[`']([^`']+)[`']",
        text,
    ):
        meta[m.group(1)] = {"colour": m.group(2), "iconPath": m.group(3)}
    return meta


def update_homepage_count(total):
    """Patch every static, hand-written mention of the total entry count —
    the homepage's pre-JS count fallbacks, plus its and map.html's meta/OG/
    Twitter descriptions (search-snippet copy, so it's worth keeping honest).
    Rounded down to the nearest 50 and shown as "X+", or just "X" with no
    "+" if the total happens to land on an exact multiple of 50 — matches
    roundedCountPlus() in index.html's own script, which overwrites the
    heroCount/statLegends spans at runtime once legends.json loads, so the
    two must stay in lockstep."""
    rounded_num = (total // 50) * 50
    rounded = f"{rounded_num}+" if rounded_num < total else str(rounded_num)

    path = "index.html"
    text = io.open(path, encoding="utf-8").read()
    patterns = (
        (r'(<span id="heroCount">)[^<]*(</span>)', rf'\g<1>{rounded}\g<2>'),
        (r'(<span class="stat-num" id="statLegends">)[^<]*(</span>)', rf'\g<1>{rounded}\g<2>'),
        (r'(sacred sites across )\d+\+?( locations)', rf'\g<1>{rounded}\g<2>'),
    )
    for pattern, replacement in patterns:
        text, changed = re.subn(pattern, replacement, text, count=1)
        if changed != 1:
            raise RuntimeError(f"Could not update homepage count using {pattern}")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)

    map_path = "map.html"
    map_text = io.open(map_path, encoding="utf-8").read()
    map_text, changed = re.subn(r'\d+\+? entries', f'{rounded} entries', map_text, count=1)
    if changed != 1:
        raise RuntimeError("Could not update map.html description count")
    map_text, changed = re.subn(r'Explore \d+\+? myths', f'Explore {rounded} myths', map_text)
    if changed != 2:
        raise RuntimeError("Could not update map.html og/twitter description counts")
    with io.open(map_path, "w", encoding="utf-8") as f:
        f.write(map_text)


NEW_COLLECTIONS_STATE_FILE = "collections_state.json"


def update_whats_new_page(recent, built_collections, slugmap, cats, meta, limit=8):
    """Inject the Recently Added Legends / New Collections cards into updates.html.
    Release notes further down the page stay hand-written — this only touches the
    two placeholder arrays. "New" collections are those not seen in a previous
    build, tracked via NEW_COLLECTIONS_STATE_FILE so the list empties out over time
    rather than re-announcing every collection on every run."""
    recent_cards = [
        {
            "slug": slugmap[l["name"]],
            "name": l["name"],
            "date_added": human_date(l.get("date_added")),
            "region": l.get("region", ""),
            "category": cats.get(l.get("category", ""), l.get("category", "")),
            "colour": meta.get(l.get("category", ""), {}).get("colour", "#8b3a1a"),
        }
        for l in recent[:limit]
    ]

    path = "updates.html"
    text = io.open(path, encoding="utf-8").read()

    try:
        seen_slugs = set(json.load(io.open(NEW_COLLECTIONS_STATE_FILE, encoding="utf-8")))
    except Exception:
        seen_slugs = set()
    current_slugs = {slug for slug, _, _ in built_collections}
    new_cards = [
        {"slug": slug, "title": title}
        for slug, title, _count in built_collections
        if slug not in seen_slugs
    ]
    if not new_cards:
        match = re.search(r"const NEW_COLLECTIONS = (.*?);", text, flags=re.S)
        if match:
            try:
                existing_cards = json.loads(match.group(1))
            except Exception:
                existing_cards = []
            titles_by_slug = {slug: title for slug, title, _count in built_collections}
            new_cards = [
                {"slug": card["slug"], "title": titles_by_slug[card["slug"]]}
                for card in existing_cards
                if isinstance(card, dict) and card.get("slug") in current_slugs
            ]
    with io.open(NEW_COLLECTIONS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(current_slugs), f, ensure_ascii=False, indent=0)

    # Matches both the initial placeholder and a previously-injected array, so
    # re-running the build stays idempotent.
    replacements = (
        (r"const RECENT_LEGENDS = .*?;",
         "const RECENT_LEGENDS = " + json.dumps(recent_cards, ensure_ascii=False) + ";"),
        (r"const NEW_COLLECTIONS = .*?;",
         "const NEW_COLLECTIONS = " + json.dumps(new_cards, ensure_ascii=False) + ";"),
    )
    for pattern, replacement in replacements:
        text, changed = re.subn(pattern, lambda m: replacement, text, count=1)
        if changed != 1:
            raise RuntimeError(f"Could not update updates.html using {pattern}")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def render_featured_legend(leg, featured, paras, srcs, rel, nearby, cats, meta,
                           slugmap, catname, maplink, page_path_url, desc,
                           jsonld, breadcrumb, breadcrumb_jsonld, collections=(),
                           periods_by_title=None, featured_pages=None, sightings=None):
    """Render the editorial legend layout, with artwork when available."""
    name = leg["name"]
    image_path = featured.get("image", "")
    has_image = bool(image_path)
    if has_image and not os.path.isfile(image_path):
        raise RuntimeError(f"Featured legend image is missing for {name}: {image_path}")

    featured_parts = []
    if paras:
        featured_parts.append(f'<p class="opening">{esc(inline_text(paras[0]))}</p>')
    pullquote = featured.get("pullquote")
    if pullquote:
        featured_parts.append(f'<blockquote class="pullquote">{esc(inline_text(pullquote))}</blockquote>')
    if len(paras) > 1:
        section_heading = title_case_text(featured.get("section_heading") or "The story")
        featured_parts.append(f"<h2>{esc(section_heading)}</h2>")
        featured_parts.extend(f"<p>{esc(inline_text(p))}</p>" for p in paras[1:])
    featured_body = "".join(featured_parts) or '<p class="opening"></p>'

    # Editor's note — a curated, named editorial aside (a deliberate human-voice
    # signal). Taken from featured metadata or the legend's own `editorial` field;
    # rendered only when written. `editorial_by` supplies the byline.
    editorial = featured.get("editorial") or leg.get("editorial")
    if editorial:
        by = (featured.get("editorial_by") or leg.get("editorial_by")
              or "Folklore Map editors")
        editorial_html = (
            '<aside class="editor-note" aria-label="Editor\'s note">'
            '<p class="editor-kicker">Editor&#8217;s note</p>'
            f'<p>{esc(inline_text(editorial))}</p>'
            f'<p class="editor-by">&#8212; {esc(by)}</p></aside>'
        )
    else:
        editorial_html = ""

    # Historical Context — origin date, earliest record, period, setting,
    # tradition and dating confidence, when the entry has any of them. Dates in
    # folklore are often approximate (many traditions predate any surviving
    # written source), so the caveat is shown whenever the section renders.
    period_value = leg.get("period", "")
    period_slug = (periods_by_title or {}).get(period_value)
    period_display = (
        f'<a href="{period_page_url(period_slug)}">{esc(period_value)}</a>'
        if period_slug else esc(period_value)
    ) if period_value else None
    # Trimmed to the fields that can be populated corpus-wide (with uncertainty
    # caveats): approximate origin, earliest written record, and the period
    # (which links to the time-filter page). Setting/tradition/dating-confidence
    # were dropped — the general caveat below already conveys the uncertainty.
    hist_fields = [
        ("Approximate Origin", esc(leg.get("origin_date")) if leg.get("origin_date") else None),
        ("Historical Period", period_display),
        ("Earliest Written Record", esc(leg.get("earliest_record")) if leg.get("earliest_record") else None),
    ]
    hist_items = [(label, val) for label, val in hist_fields if val]
    if hist_items:
        # Stacked single-column, unlike the 2-column .facts grid used elsewhere
        # in the sidebar: these values (dates, source descriptions) run much
        # longer than the About/Region facts, and squeezed into a half-width
        # sidebar column they wrapped into a tall, ragged mess.
        hist_facts_html = "".join(
            f'<div class="fact"><span>{esc(label)}</span><strong>{val}</strong></div>'
            for label, val in hist_items
        )
        historical_context = (
            '<section class="side-card side-pad">'
            + side_head("Historical Context", "Origins &amp; Dating", "hourglass") +
            f'<div class="facts facts-stacked">{hist_facts_html}</div>'
            '<p class="hist-caveat">Folklore dates are often approximate, especially '
            'where a story predates any surviving written source.</p></section>'
        )
    else:
        historical_context = ""

    fact_items = featured.get("facts") or {
        "Category": catname,
        "Region": leg.get("region", ""),
    }
    facts_html = "".join(
        f'<div class="fact"><span>{esc(title_case_text(label))}</span><strong>{esc(title_case_text(value))}</strong></div>'
        for label, value in fact_items.items()
    )
    # Paired with the map card as the sidebar's top row (see .sidebar's 2-column
    # grid in legend-page.css) — always present, so it's a reliable partner for
    # the map regardless of which optional cards a given entry has.
    featured_facts = (
        '<section class="side-card side-pad">'
        + side_head("At a Glance", "About This Legend", "scroll-text") +
        f'<div class="facts">{facts_html}</div></section>'
    )

    # Recent Sightings — curated news coverage of modern reports for the small
    # subset of legends with an active sighting culture (cryptids, big-cat
    # reports, etc.). Entries older than the freshness window are dropped at
    # build time so the box can't calcify into stale news; a legend with no
    # current entries gets no box at all rather than an empty placeholder.
    SIGHTING_FRESHNESS_DAYS = 730
    fresh_sightings = []
    for s in (sightings or []):
        try:
            age = (datetime.date.today() - datetime.datetime.strptime(s["date"], "%Y-%m-%d").date()).days
        except Exception:
            continue
        if age <= SIGHTING_FRESHNESS_DAYS:
            fresh_sightings.append(s)
    fresh_sightings.sort(key=lambda s: s["date"], reverse=True)
    if fresh_sightings:
        sighting_items = []
        for s in fresh_sightings:
            flag = (
                '<span class="sighting-flag">Possible sighting</span>'
                if s.get("confidence") == "possible" else ""
            )
            sighting_items.append(
                f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">'
                f'<span class="sighting-date">{esc(human_date(s["date"]))}</span>'
                f'<span class="sighting-title">{esc(s["title"])}</span></a>'
                f'<span class="sighting-source">{esc(s["source_name"])}</span>{flag}</li>'
            )
        featured_sightings = (
            '<section class="side-card side-pad">'
            + side_head("Recent Sightings", "Reported in the Wild", "eye") +
            '<p class="source-copy">Recent news coverage mentioning this legend.</p>'
            f'<ul class="sighting-list">{"".join(sighting_items)}</ul></section>'
        )
    else:
        featured_sightings = ""

    if srcs:
        def source_item(s):
            chip = (
                f'<span class="src-tier" data-tier="{esc(s["tier"])}">'
                f'{esc(TIER_CHIPS[s["tier"]])}</span>'
            ) if s.get("tier") in TIER_CHIPS else ""
            return (
                f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">'
                f'<span class="src-name">{esc(s["publisher"])} &#8594;</span>'
                f'{chip}</a></li>'
            )

        source_items = "".join(source_item(s) for s in srcs)
        # Small provenance line, not a headline stat — a previous pass tried
        # date_added more prominently and it "looked out of place" (see the
        # dropped JSON-LD-only comment above); tucking it under the source
        # list instead reads as quiet metadata rather than a marketing stat.
        added_raw = leg.get("date_added")
        added_html = (
            f'<p class="hist-caveat">Added to the map {esc(human_date(added_raw))}.</p>'
            if added_raw else ""
        )
        featured_sources = (
            '<section class="side-card side-pad">'
            + side_head("Sources", "Further Reading", "book-open") +
            '<p class="source-copy">Sources used to research and locate this legend.</p>'
            f'<ul class="source-list">{source_items}</ul>{added_html}</section>'
        )
    else:
        featured_sources = ""

    # Nearby legends — geographically closest entries (distinct from the
    # tag-weighted related list); ties the page back to the mini-map.
    nearby_items = []
    for nb, dist in nearby:
        dist_label = "&lt;1 km" if dist < 1 else f"{round(dist)} km"
        nb_colour = meta.get(nb.get("category", ""), {}).get("colour", "#8b3a1a")
        nearby_items.append(
            f'<li><a href="{BASE}/{OUT_DIR}/{slugmap[nb["name"]]}">'
            f'<span class="nearby-dot" style="background:{esc(nb_colour)}" aria-hidden="true"></span>'
        f'<span class="nearby-name">{esc(title_case_text(nb["name"]))}</span>'
            f'<span class="nearby-dist">{dist_label}</span></a></li>'
        )
    if nearby_items:
        featured_nearby = (
            '<section class="side-card side-pad">'
            + side_head("In the Area", "Nearby Legends", "compass") +
            f'<ul class="nearby-list">{"".join(nearby_items)}</ul></section>'
        )
    else:
        featured_nearby = ""

    # Part of these Collections — links back to any themed collection this
    # legend belongs to, so a visitor can jump from one entry into a broader
    # curated gathering rather than only the map/category/region views.
    if collections:
        collection_items = "".join(
            f'<li><a href="{BASE}/{OUT_DIR}/collection/{esc(slug)}">{esc(title)}</a></li>'
            for slug, title in collections
        )
        featured_collections = (
            '<section class="side-card side-pad">'
            + side_head("Part of", "These Collections", "library") +
            f'<ul class="collections-list">{collection_items}</ul></section>'
        )
    else:
        featured_collections = ""

    # Emit 6 candidates (compute_related keeps up to 10, ranked by relevance)
    # instead of just the top 3 — legend-page.js picks the 3 actually shown,
    # preferring ones not yet in ff_visited_legends_v1, so a repeat visitor
    # gets steered toward something new rather than the same 3 every time.
    # Cards beyond the first 3 start hidden (.extra) so there's no flash of
    # 6 cards before JS runs, and it degrades gracefully with JS disabled.
    featured_cards = []
    for idx, related in enumerate(rel[:6]):
        related_cat = cats.get(related.get("category", ""), related.get("category", ""))
        related_colour = meta.get(related.get("category", ""), {}).get("colour", "#8b3a1a")
        rslug = slugmap[related["name"]]
        # Show the related legend's hero artwork as the card background when it
        # exists. Use the STORED image path, not a slug-derived filename: some
        # names slugify differently from how their image was named (e.g.
        # apostrophes — "St Michael's" -> slug "michael-s" but file "michaels"),
        # which was hiding real preview images (e.g. Cormoran).
        rel_img = featured_pages.get(related["name"], {}).get("image", "")
        if rel_img and os.path.isfile(rel_img):
            jpg_u = f"{BASE}/{rel_img.replace(os.sep, '/')}"
            # Prefer WebP (with JPEG fallback via image-set) — related cards load
            # the full hero as a background, so this is a real weight saving.
            # Prefer the card-sized thumb over the full hero: the card only ever
            # paints a ~469px-wide box, so the 1600px hero is ~3x oversized.
            base_path = rel_img.rsplit(".", 1)[0]
            thumb_path = base_path + "-card.webp"
            webp_path = base_path + ".webp"
            webp_src = thumb_path if os.path.isfile(thumb_path) else webp_path
            if os.path.isfile(webp_src):
                webp_u = f"{BASE}/{webp_src.replace(os.sep, '/')}"
                card_img = (f"image-set(url('{webp_u}') type('image/webp'), "
                            f"url('{jpg_u}') type('image/jpeg'))")
            else:
                card_img = f"url('{jpg_u}')"
            card_cls, card_style = "related-card has-img", f"--card-img:{card_img}"
        else:
            card_cls, card_style = "related-card", f'--card-glow:{esc(related_colour)}'
        if idx >= 3:
            card_cls += " extra"
        featured_cards.append(
            f'<a class="{card_cls}" style="{card_style}" '
            f'href="{BASE}/{OUT_DIR}/{rslug}">'
            f'<span class="related-type">{esc(related_cat)}</span>'
            f'<span class="related-name">{esc(related["name"])}</span>'
            f'<span class="related-place">{esc(related.get("region", ""))}</span></a>'
        )
    if featured_cards:
        featured_related = (
            '<section class="related"><div class="shell">'
            '<div class="section-head"><div><p>Continue Exploring</p>'
            '<h2>Related Legends</h2></div>'
            f'<a href="{BASE}/{OUT_DIR}/">Browse All Legends</a></div>'
            f'<div class="related-grid">{"".join(featured_cards)}</div>'
            '</div></section>'
        )
    else:
        featured_related = ""

    lat = float(leg.get("lat"))
    lng = float(leg.get("lng"))
    coordinates = (
        f"{abs(lat):.3f} {'N' if lat >= 0 else 'S'}, "
        f"{abs(lng):.3f} {'E' if lng >= 0 else 'W'}"
    )
    catcolour = meta.get(leg.get("category", ""), {}).get("colour", "#8b3a1a")

    # Map card — always present, first in reading order. Built as a variable
    # (rather than fixed markup in FEATURED_PAGE) so it can take part in the
    # two-column split below like every other sidebar card.
    featured_map = (
        '<section class="side-card">'
        '<div class="side-pad"><p class="side-kicker">Explore the Place</p>'
        f'<h2>{lucide("map-pin", 19, "side-icon")}'
        f'{esc(title_case_text(featured.get("map_title") or leg.get("region", "")))}</h2>'
        f'<p class="map-meta">{esc(leg.get("region", ""))}</p></div>'
        f'<div id="miniMap" data-lat="{lat:.6f}" data-lng="{lng:.6f}" data-colour="{esc(catcolour)}" '
        f'data-initial="{esc(name[:1])}" aria-label="Map showing the location associated with {esc(name)}"></div>'
        f'<div class="map-footer"><a href="{esc(maplink)}">View Full Map &#8594;</a>'
        f'<span>{coordinates}</span></div></section>'
    )

    # Two independent column stacks, not a row-locked grid: a shorter card in
    # column A must not leave a gap before the next column-A card just because
    # column B's card in that "row" happened to be taller. Alternate the fixed
    # reading-priority order into two lists instead — each renders as its own
    # flex column (see .sidebar/.sidebar-col in legend-page.css), so every card
    # sits flush under the one above it in its own column. Map+At a Glance and
    # Nearby+Origins&Dating still land as the first two cards of each column
    # (matching the requested pairing); any optional cards beyond that split
    # evenly by simple alternation, which is as much "balancing" as static HTML
    # can do without knowing real rendered heights.
    sidebar_sections = [s for s in (
        featured_map, featured_facts, featured_nearby, historical_context,
        featured_sightings, featured_collections, featured_sources,
    ) if s]
    sidebar_col1 = "".join(sidebar_sections[0::2])
    sidebar_col2 = "".join(sidebar_sections[1::2])
    if has_image:
        hero_url = f"{BASE}/{image_path.replace(os.sep, '/')}"
        hero_alt = esc(featured.get("alt", ""))
        # WebP with JPEG fallback. The hero is the LCP image, so load it eagerly
        # with high priority (never lazy). width/height reserve the 16:9 box to
        # avoid layout shift. The <source> is only added when the webp exists.
        webp_rel = image_path.rsplit(".", 1)[0] + ".webp"
        img_tag = (f'<img src="{hero_url}" alt="{hero_alt}" '
                   f'width="1600" height="900" fetchpriority="high" decoding="async"/>')
        if os.path.isfile(webp_rel):
            webp_url = f"{BASE}/{webp_rel.replace(os.sep, '/')}"
            hero_media = (f'<picture><source type="image/webp" srcset="{webp_url}"/>'
                          f'{img_tag}</picture>')
        else:
            hero_media = img_tag
        # Hero art is AI-generated (Codex), so the disclosure note is always
        # shown here regardless of whether an editorial caption exists —
        # see the editorial & AI-use policy at /editorial.
        caption_span = (
            f'<span class="hero-caption">{esc(featured.get("caption", ""))}</span>'
            if featured.get("caption") else ""
        )
        ai_note_span = '<span class="hero-ai-note">Illustration created with the assistance of generative AI.</span>'
        # The caption wrap is nested INSIDE hero-media-wrap (with the image),
        # not left as a sibling of the whole hero section — on mobile the
        # hero stacks image-then-text instead of overlaying, so a caption
        # positioned against the full hero box used to land over the title
        # text instead of the image. Scoping it to a wrapper that's sized to
        # just the image keeps it correctly placed in both layouts.
        hero_caption_html = f'<div class="hero-caption-wrap">{caption_span}{ai_note_span}</div>'
        hero_media = f'<div class="hero-media-wrap">{hero_media}{hero_caption_html}</div>'
        hero_caption = ""
        ogimage = hero_url
        og_w, og_h = "1600", "900"  # Codex hero artwork is 16:9 at this size
        og_alt = featured.get("alt") or f"Illustration of {name}"
    else:
        icon_path = meta.get(leg.get("category", ""), {}).get("iconPath", "")
        hero_media = (
            f'<div class="hero-placeholder" role="img" '
            f'aria-label="Illustration placeholder for {esc(name)}" '
            f'style="--placeholder-colour:{esc(catcolour)}">'
            '<div class="placeholder-lines" aria-hidden="true"></div>'
            f'<svg viewBox="0 0 512 512" aria-hidden="true"><path d="{esc(icon_path)}"/></svg>'
            '<span>Illustration in preparation</span></div>'
        )
        hero_caption = ""
        ogimage = (
            f"{BASE}/og/category-{leg.get('category', '')}.png"
            if leg.get("category", "") in meta else f"{BASE}/og/preview.jpg"
        )
        og_w, og_h = "1200", "630"  # category / preview OG cards
        og_alt = f"{name} — {catname}, folklore of Britain & Ireland"

    return FEATURED_PAGE.substitute(
        title=esc(featured.get("seo_title") or f"{name} — Folklore Finder"),
        ogtitle=esc(name),
        desc=esc(inline_text(desc)),
        url=page_path_url,
        base=BASE,
        jsonld=jsonld,
        breadcrumb_jsonld=breadcrumb_jsonld,
        topnav=topnav_html("browse"),
        footer=footer_html(),
        breadcrumb=breadcrumb,
        hero_media=hero_media,
        hero_caption=hero_caption,
        catcolour=esc(catcolour),
        catname=esc(catname),
        region=esc(leg.get("region", "")),
        name=esc(name),
        pronunciation=(
            f'<p class="pronunciation">{esc(leg.get("pronunciation"))}</p>'
            if leg.get("pronunciation") else ""
        ),
        standfirst=esc(inline_text(leg.get("summary", ""))),
        featured_body=featured_body,
        editorial=editorial_html,
        maplink=esc(maplink),
        icon_map=lucide("map", 13),
        icon_link=lucide("link", 13),
        icon_share=lucide("share-2", 13),
        sidebar_col1=sidebar_col1,
        sidebar_col2=sidebar_col2,
        featured_related=featured_related,
        ogimage=ogimage,
        og_w=og_w,
        og_h=og_h,
        og_alt=esc(og_alt),
    )


def build():
    d = json.load(io.open("legends.json", encoding="utf-8"))
    cats = d.get("categories", {})
    legends = sorted(d["legends"], key=lambda l: l["name"].lower())
    today = datetime.date.today().isoformat()
    resolve_modified_dates(legends, today)  # stamps each leg["date_modified"]
    update_homepage_count(len(legends))
    meta = load_category_meta()
    cat_intros, region_intros = load_page_intros()
    featured_pages = load_featured_pages()
    os.makedirs(OUT_DIR, exist_ok=True)

    # Convert hero JPGs to WebP (auto-picks up newly-added images each build)
    build_webp_heroes()
    # ...and a card-sized thumb for the related-legend cards on every legend page
    build_card_thumbs()

    # Slim achievement index — legend pages fetch this (not the full 1.3 MB
    # legends.json) purely to evaluate achievement-toast criteria, which only
    # needs name/category/region. See legend-page.js checkAchievementToasts().
    slim_index = {"legends": [
        {"name": l.get("name"), "category": l.get("category"), "region": l.get("region")}
        for l in legends
    ]}
    with io.open("legends-index.json", "w", encoding="utf-8") as f:
        json.dump(slim_index, f, ensure_ascii=False, separators=(",", ":"))

    # Unique slugs
    slugmap, seen = {}, set()
    for leg in legends:
        b = slugify(leg["name"])
        s, i = b, 2
        while s in seen:
            s = f"{b}-{i}"; i += 1
        seen.add(s)
        slugmap[leg["name"]] = s

    # Group entries once — used for browse pages AND per-legend breadcrumbs
    cat_groups, region_groups = {}, {}
    for leg in legends:
        cat_groups.setdefault(leg.get("category", ""), []).append(leg)
        for tag in (set(leg.get("tags") or []) - THEMATIC_TAGS):
            region_groups.setdefault(tag, []).append(leg)
    generated_regions = {t for t in region_groups if t in NATIONS or len(region_groups[t]) >= 4}

    def breadcrumb_for(leg):
        """Legends > Category > Region (most specific page that exists)."""
        parts = [("Legends", f"{BASE}/{OUT_DIR}/")]
        cat = leg.get("category", "")
        if cat in cat_groups:
            parts.append((cats.get(cat, cat), f"{BASE}/{OUT_DIR}/category/{cat}"))
        rtags = (set(leg.get("tags") or []) - THEMATIC_TAGS) & generated_regions
        counties = sorted(t for t in rtags if t not in NATIONS)
        nats = sorted(t for t in rtags if t in NATIONS)
        rtag = counties[0] if counties else (nats[0] if nats else None)
        if rtag:
            parts.append((prettify_region(rtag), f"{BASE}/{OUT_DIR}/region/{rtag}"))
        return parts

    related_map = compute_related(legends)
    nearby_map = compute_nearby(legends)

    # Themed-collection membership, resolved once so both the per-legend
    # "Part of these Collections" sidebar and the collection pages themselves
    # (below) use the same qualifying set (>= MIN_COLLECTION members).
    collections = load_collections()
    legends_by_name = {l["name"]: l for l in legends}
    collection_members = []  # (col, members) for collections that qualify
    for col in collections:
        explicit = col.get("members")
        if explicit is not None:
            # Hand-curated membership (from the review worksheet): use the exact
            # list, in the given order, and always render it — the curator chose
            # these deliberately, so the MIN_COLLECTION gate does not apply.
            members = [legends_by_name[n] for n in explicit if n in legends_by_name]
            collection_members.append((col, members))
        else:
            members = sorted(
                (l for l in legends if matches_collection(l, col.get("match", {}))),
                key=lambda l: l["name"].lower(),
            )
            if len(members) >= MIN_COLLECTION:
                collection_members.append((col, members))
    legend_collections_map = {}
    for col, members in collection_members:
        for l in members:
            legend_collections_map.setdefault(l["name"], []).append((col["slug"], col["title"]))

    # Explore Through Time — every canonical period gets a page regardless of
    # how many legends currently carry it (a fixed historical framework, not
    # a curated collection that should stay hidden while thin).
    periods = load_periods()
    periods_by_title = {p["match"]: p["slug"] for p in periods}
    sightings_map = load_sightings()
    period_members = {p["slug"]: [] for p in periods}
    for l in legends:
        slug = periods_by_title.get(l.get("period"))
        if slug:
            period_members[slug].append(l)
    for slug in period_members:
        period_members[slug].sort(key=lambda l: l["name"].lower())

    written = 0
    for leg in legends:
        name = leg["name"]
        slug = slugmap[name]
        desc = short_desc(leg.get("summary", ""))
        # Full-page body: use the longer `detail` if present, else the summary.
        # Split on blank lines into paragraphs; first paragraph gets the drop cap.
        body_text = leg.get("detail") or leg.get("summary", "")
        paras = [p.strip() for p in body_text.split("\n\n") if p.strip()]
        catname = cats.get(leg.get("category", ""), leg.get("category", "Legend"))
        maplink = f"{BASE}/map?legend=" + urllib.parse.quote(name)
        srcs = legend_sources(leg)
        added = leg.get("date_added")
        modified = leg.get("date_modified")
        ld = {
            "@context": "https://schema.org",
            "@type": "CreativeWork",
            "name": name,
            "description": desc,
            "url": f"{BASE}/{OUT_DIR}/{slug}",
            "genre": "Folklore",
            "about": {
                "@type": "Place",
                "name": leg.get("region", ""),
                "geo": {"@type": "GeoCoordinates",
                        "latitude": leg.get("lat"), "longitude": leg.get("lng")},
            },
            "isPartOf": {"@type": "WebSite",
                         "name": "Folklore Finder", "url": BASE + "/"},
        }
        if added:
            ld["datePublished"] = added
        if modified:
            ld["dateModified"] = modified
        if srcs:
            based = [{"@type": "CreativeWork", "url": s["url"],
                      "publisher": {"@type": "Organization", "name": s["publisher"]}}
                     for s in srcs]
            ld["isBasedOn"] = based[0] if len(based) == 1 else based
        # date_added/date_modified stay in the JSON-LD and sitemap, but are not
        # shown on the page (looked out of place).

        # Related legends carousel
        rel = related_map.get(name, [])

        page_path_url = f"{BASE}/{OUT_DIR}/{slug}"
        featured_meta = featured_pages.get(name, {})
        hero_image_path = featured_meta.get("image", "")
        if hero_image_path:
            hero_schema_image = image_object(
                hero_image_path,
                featured_meta.get("alt") or f"{name} hero artwork",
                featured_meta.get("caption", ""),
                1600,
                900,
            )
            if hero_schema_image:
                ld["image"] = hero_schema_image
                ld["thumbnailUrl"] = hero_schema_image["contentUrl"]
                ld["primaryImageOfPage"] = hero_schema_image
        ld["mainEntityOfPage"] = {
            "@type": "WebPage",
            "@id": page_path_url,
            "url": page_path_url,
            "name": f"{name} — Folklore Finder",
        }
        ld["keywords"] = [catname, leg.get("region", "")] + sorted(leg.get("tags") or [])
        if rel:
            ld["hasPart"] = {
                "@type": "ItemList",
                "name": f"Related legends for {name}",
                "itemListOrder": "https://schema.org/ItemListOrderAscending",
                "numberOfItems": len(rel),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{BASE}/{OUT_DIR}/{slugmap[r['name']]}",
                        "name": r["name"],
                    }
                    for i, r in enumerate(rel)
                ],
            }
        jsonld = json.dumps(ld, ensure_ascii=False)

        # Breadcrumb: Legends > Category > Region > Name (visible + structured data)
        crumb_parts = breadcrumb_for(leg)
        breadcrumb = '<nav class="crumb" aria-label="Breadcrumb">' + "".join(
            f'<a href="{u}">{esc(lbl)}</a><span class="sep">&#8250;</span>' for lbl, u in crumb_parts
        ) + f'<span class="here">{esc(name)}</span></nav>'
        crumb_items = [
            {"@type": "ListItem", "position": i + 1, "name": lbl, "item": u}
            for i, (lbl, u) in enumerate(crumb_parts)
        ]
        crumb_items.append({"@type": "ListItem", "position": len(crumb_parts) + 1,
                            "name": name, "item": page_path_url})
        breadcrumb_jsonld = '<script type="application/ld+json">' + json.dumps(
            breadcrumb_list([(item["name"], item["item"]) for item in crumb_items]),
            ensure_ascii=False) + '</script>'

        out = render_featured_legend(
            leg=leg,
            featured=featured_pages.get(name, {}),
            featured_pages=featured_pages,
            paras=paras,
            srcs=srcs,
            rel=rel,
            nearby=nearby_map.get(name, []),
            cats=cats,
            meta=meta,
            slugmap=slugmap,
            catname=catname,
            maplink=maplink,
            page_path_url=page_path_url,
            desc=desc,
            jsonld=jsonld,
            breadcrumb=breadcrumb,
            breadcrumb_jsonld=breadcrumb_jsonld,
            collections=legend_collections_map.get(name, []),
            periods_by_title=periods_by_title,
            sightings=sightings_map.get(name, []),
        )
        with io.open(os.path.join(OUT_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(out)
        written += 1

    # ── Browse-by-category & browse-by-region pages ────────────────────────
    cat_dir = os.path.join(OUT_DIR, "category")
    reg_dir = os.path.join(OUT_DIR, "region")
    os.makedirs(cat_dir, exist_ok=True)
    os.makedirs(reg_dir, exist_ok=True)

    browse_urls = []

    # Category pages
    cat_order = sorted(cat_groups, key=lambda c: -len(cat_groups[c]))
    cat_nav_items = [(f"{BASE}/{OUT_DIR}/category/{c}", cats.get(c, c), c) for c in cat_order]
    for c in cat_order:
        entries = sorted(cat_groups[c], key=lambda l: l["name"].lower())
        label = cats.get(c, c)
        url = f"{BASE}/{OUT_DIR}/category/{c}"
        cards = "\n".join(browse_card(l, slugmap, cats, meta, show_cat=False) for l in entries)
        cat_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": label,
            "description": f"Browse {len(entries)} {label.lower()} from across British and Irish folklore.",
            "url": url,
            "isPartOf": {"@type": "WebSite", "name": "Folklore Finder", "url": BASE + "/"},
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": len(entries),
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "url": f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}", "name": l["name"]}
                    for i, l in enumerate(entries)
                ],
            },
            "image": image_object(f"og/category-{c}.png", f"{label} folklore category artwork")
            if c in meta else image_object("og/preview.jpg", "Folklore Finder preview artwork"),
        }, ensure_ascii=False)
        page = build_browse_page(
            page_title=CATEGORY_TITLES.get(c) or f"{label} of Britain & Ireland — Folklore Map",
            desc=f"Browse {len(entries)} {label.lower()} from across British and Irish folklore — each pinned to the place its story is rooted.",
            url=url,
            h1=label,
            intro=cat_intros.get(c) or f"{len(entries)} {label.lower()} and related folklore from across Britain and Ireland.",
            crumb=label,
            nav_html=nav_links(cat_nav_items, c),
            cards_html=cards,
            ogimage=f"{BASE}/og/category-{c}.png" if c in meta else None,
            jsonld=cat_jsonld,
        )
        with io.open(os.path.join(cat_dir, f"{c}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        browse_urls.append(url)

    # Region pages — nations always, other areas only if >= 4 entries (avoid thin pages)
    region_eligible = [t for t in region_groups if t in NATIONS or len(region_groups[t]) >= 4]
    region_order = sorted(region_eligible, key=lambda t: (0 if t in NATIONS else 1, -len(region_groups[t])))
    nation_nav_items = [(f"{BASE}/{OUT_DIR}/region/{t}", prettify_region(t), t)
                        for t in NATIONS if t in region_groups]
    for t in region_order:
        entries = sorted(region_groups[t], key=lambda l: l["name"].lower())
        rn = prettify_region(t)
        url = f"{BASE}/{OUT_DIR}/region/{t}"
        cards = "\n".join(browse_card(l, slugmap, cats, meta, show_cat=True) for l in entries)
        region_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": f"Folklore of {rn}",
            "description": f"{len(entries)} myths, legends, ghosts and folklore entries rooted in {rn}.",
            "url": url,
            "isPartOf": {"@type": "WebSite", "name": "Folklore Finder", "url": BASE + "/"},
            "about": {"@type": "Place", "name": rn},
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": len(entries),
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "url": f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}", "name": l["name"]}
                    for i, l in enumerate(entries)
                ],
            },
        }, ensure_ascii=False)
        page = build_browse_page(
            page_title=NATION_TITLES.get(t) or f"Folklore of {rn} — Myths & Legends",
            desc=f"Discover {len(entries)} myths, legends, ghosts and folklore stories rooted in {rn}, each pinned to its exact location on our interactive folklore map.",
            url=url,
            h1=f"Folklore of {rn}",
            intro=region_intros.get(t) or f"{len(entries)} legends, ghosts and folklore entries rooted in {rn}.",
            crumb=rn,
            nav_html=nav_links(nation_nav_items, t),
            cards_html=cards,
            jsonld=region_jsonld,
        )
        with io.open(os.path.join(reg_dir, f"{t}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        browse_urls.append(url)

    # ── Themed collection pages (curated, cross-cutting) ───────────────────
    col_dir = os.path.join(OUT_DIR, "collection")
    built_collections = []  # (slug, title, count) for nav / index / sitemap
    if collection_members:
        os.makedirs(col_dir, exist_ok=True)
        # Membership was already resolved above (collection_members), shared
        # with the per-legend "Part of these Collections" sidebar.
        resolved = collection_members
        col_nav_items = [
            (f"{BASE}/{OUT_DIR}/collection/{col['slug']}", col["title"], col["slug"])
            for col, _ in resolved
        ]
        for col, members in resolved:
            slug = col["slug"]
            total = len(members)
            desc = short_desc(col["intro"], 155)

            # Precomputed member name-list for the map's `?collection=` filter —
            # map.html fetches this rather than porting matches_collection() to JS.
            with io.open(os.path.join(col_dir, f"{slug}.json"), "w", encoding="utf-8") as f:
                json.dump({"legends": [m["name"] for m in members]}, f, ensure_ascii=False)
            total_pages = max(1, (total + COLLECTION_PER_PAGE - 1) // COLLECTION_PER_PAGE)
            for page_no in range(1, total_pages + 1):
                start = (page_no - 1) * COLLECTION_PER_PAGE
                page_members = members[start:start + COLLECTION_PER_PAGE]
                url = collection_page_url(slug, page_no)
                cards = collection_article_html(page_members, slugmap, cats, meta, featured_pages)
                # Page 2+ get a "(page N of M)" suffix in title/intro for clarity.
                page_tag = "" if total_pages == 1 else f" (page {page_no} of {total_pages})"
                member_images = [
                    featured_pages.get(m["name"], {}).get("image", "") for m in members
                ]
                member_images = [p for p in member_images if p]
                hero_legend_img = featured_pages.get(col.get("hero_legend", ""), {}).get("image", "")
                hero_path = hero_legend_img or col.get("hero_image") or (member_images[0] if member_images else "")
                collection_ld = {
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": col["title"] + page_tag,
                    "description": desc,
                    "url": url,
                    "isPartOf": {"@type": "WebSite",
                                 "name": "Folklore Finder", "url": BASE + "/"},
                    "mainEntity": {
                        "@type": "ItemList",
                        "numberOfItems": len(page_members),
                        "itemListElement": [
                            {"@type": "ListItem", "position": start + i + 1,
                             "url": f"{BASE}/{OUT_DIR}/{slugmap[m['name']]}", "name": m["name"]}
                            for i, m in enumerate(page_members)
                        ],
                    },
                }
                if hero_path:
                    collection_ld["primaryImageOfPage"] = image_object(
                        hero_path,
                        f"{col['title']} collection artwork",
                        col.get("hero_credit", ""),
                    )
                if member_images:
                    collection_ld["image"] = [
                        image_object(p, f"{col['title']} gallery image")
                        for p in member_images[:8]
                    ]
                collection_jsonld = json.dumps(collection_ld, ensure_ascii=False)
                # rel=prev/next help crawlers understand the paginated series.
                rel_links = ""
                if page_no > 1:
                    rel_links += f'<link rel="prev" href="{collection_page_url(slug, page_no - 1)}"/>\n'
                if page_no < total_pages:
                    rel_links += f'<link rel="next" href="{collection_page_url(slug, page_no + 1)}"/>\n'

                # Editorial content on page 1 only: a compact hero and the
                # collection's context folded into the summary. The "browse other
                # collections" nav now sits
                # at the top (top_nav_html), and each member's own image appears in
                # its article row, so the old gallery / related-collections sections
                # are dropped as redundant.
                # Page 1 leads with a split hero: the description on the left and
                # the collection's iconic image on the right, at the same level.
                # The description lives inside the split, so the plain intro
                # paragraph is suppressed on page 1 (page_intro=""); pages 2+ keep it.
                hero_html, extra_sections, context_html = "", "", ""
                page_intro = col["intro"]
                if page_no == 1:
                    page_intro = ""
                    media_html = ""
                    if hero_path:
                        # Collection hero art is drawn from the same AI-generated
                        # legend-image pool, so it carries the same disclosure.
                        hero_credit_html = (
                            f'<span class="col-hero-credit">{esc(col["hero_credit"])} &middot; '
                            'Illustration created with the assistance of generative AI.</span>'
                            if col.get("hero_credit") else
                            '<span class="col-hero-credit">Illustration created with the '
                            'assistance of generative AI.</span>'
                        )
                        media_html = (
                            '<div class="col-hero-media">'
                            f'<img src="{BASE}/{hero_path.replace(os.sep, "/")}" alt="{esc(col["title"])}"/>'
                            f'{hero_credit_html}</div>'
                        )
                    # Both intro paragraphs belong in the text column, stacked
                    # beside the image. Emitting the context paragraph after the
                    # split let the tall (320px, 4:3) media push it way down the
                    # page instead of sitting under the lede.
                    context_para = (
                        f'<p class="col-context">{esc(col["context"])}</p>'
                        if col.get("context") else ""
                    )
                    hero_html = (
                        '<div class="col-hero-split">'
                        f'<div class="col-hero-desc"><p>{esc(col["intro"])}</p>'
                        f'{context_para}</div>'
                        f'{media_html}</div>\n'
                    )

                map_link = (f'<p class="col-maplink"><a class="back" '
                            f'href="{BASE}/map?collection={esc(slug)}">'
                            f'View this collection on the Map &#8594;</a></p>\n')
                progress_html = (
                    '<div class="col-progress" hidden>'
                    '<span class="cip-bar"><span class="cip-fill"></span></span>'
                    '<span class="cip-label"></span>'
                    '<button type="button" class="col-share-btn" hidden>Share this collection</button>'
                    '<span class="col-share-status" aria-live="polite"></span></div>\n'
                )
                page = build_browse_page(
                    page_title=f"{col['title']}{page_tag} — Folklore Finder",
                    desc=desc,
                    url=url,
                    ogimage=(absolute_asset_url(hero_path) if hero_path else None),
                    h1=col["title"],
                    intro=page_intro,
                    crumb=col["title"] + page_tag,
                    nav_html="",
                    top_nav_html=nav_links(col_nav_items, slug),
                    cards_html=cards,
                    grid_class="col-articles",
                    jsonld=collection_jsonld,
                    head_extra=rel_links,
                    after_grid=pagination_html(slug, page_no, total_pages),
                    nav_active="collections",
                    hero_html=hero_html,
                    extra_sections=extra_sections,
                    after_intro=context_html + progress_html + map_link,
                    wrap_class="ornamented",
                    track_script=track_event_script("collection_viewed", collection_slug=slug)
                                 + collection_detail_progress_script(slug, col["title"]),
                )
                fname = f"{slug}.html" if page_no == 1 else f"{slug}-{page_no}.html"
                with io.open(os.path.join(col_dir, fname), "w", encoding="utf-8") as f:
                    f.write(page)
                browse_urls.append(url)
            built_collections.append((slug, col["title"], total))

        # Collections landing page (the "Collections" nav destination).
        if resolved:
            land_url = f"{BASE}/{OUT_DIR}/collections"
            land_cards = []
            for col, members in resolved:
                curl = collection_page_url(col["slug"], 1)
                rep = (featured_pages.get(col.get("hero_legend", ""), {}).get("image")
                       or col.get("hero_image") or next(
                    (featured_pages[m["name"]]["image"] for m in members
                     if featured_pages.get(m["name"], {}).get("image")), ""))
                media = (
                    '<div class="col-index-media">'
                    f'<img src="{BASE}/{rep.replace(os.sep, "/")}" alt="{esc(col["title"])}" loading="lazy"/></div>'
                    if rep else ""
                )
                land_cards.append(
                    f'<a class="col-index-row" href="{curl}" data-slug="{esc(col["slug"])}">' + media
                    + '<div class="col-index-body">'
                    + f'<span class="col-index-count">{len(members)} legends</span>'
                    + f'<h2 class="col-index-name">{esc(col["title"])}</h2>'
                    + f'<p class="col-index-intro">{esc(short_desc(col["intro"], 210))}</p>'
                    + '<span class="col-index-progress" hidden>'
                    + '<span class="cip-bar"><span class="cip-fill"></span></span>'
                    + '<span class="cip-label"></span></span>'
                    + '<span class="col-index-more">Explore the collection &#8594;</span>'
                    + '</div></a>'
                )
            land_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": "Themed Collections",
                "description": "Themed collections of British and Irish folklore — black dogs, "
                               "standing stones, holy wells, Arthurian places and more.",
                "url": land_url,
                "isPartOf": {"@type": "WebSite",
                             "name": "Folklore Finder", "url": BASE + "/"},
                "mainEntity": {
                    "@type": "ItemList",
                    "numberOfItems": len(resolved),
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "url": collection_page_url(col["slug"], 1), "name": col["title"]}
                        for i, (col, _) in enumerate(resolved)
                    ],
                },
            }, ensure_ascii=False)
            land_page = build_browse_page(
                page_title="Themed Collections — Folklore Finder",
                desc="Explore British and Irish folklore by theme — black dogs, standing stones, "
                     "holy wells, Arthurian places, legends of the sea and more.",
                url=land_url,
                h1="Themed Collections",
                intro="Curated gatherings of legends that share a creature, a landscape or a tradition — "
                      "ways into the map that the category and region lists don't capture.",
                crumb="Collections",
                nav_html="",
                cards_html="\n".join(land_cards),
                grid_class="col-index",
                jsonld=land_jsonld,
                nav_active="collections",
                wrap_class="ornamented",
                track_script=collection_index_progress_script(),
            )
            with io.open(os.path.join(OUT_DIR, "collections.html"), "w", encoding="utf-8") as f:
                f.write(land_page)
            browse_urls.append(land_url)

    # ── Explore Through Time (period pages) ────────────────────────────────
    period_dir = os.path.join(OUT_DIR, "period")
    if periods:
        os.makedirs(period_dir, exist_ok=True)
        period_nav_items = [
            (period_page_url(p["slug"]), p["title"], p["slug"]) for p in periods
        ]
        timeline_cards = []
        for p in periods:
            slug = p["slug"]
            members = period_members[slug]
            url = period_page_url(slug)
            cards = "\n".join(
                browse_card(l, slugmap, cats, meta, show_cat=True, show_summary=True)
                for l in members
            )
            period_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": p["title"],
                "description": short_desc(p["overview"], 155),
                "url": url,
                "isPartOf": {"@type": "WebSite", "name": "Folklore Finder", "url": BASE + "/"},
                "mainEntity": {
                    "@type": "ItemList",
                    "numberOfItems": len(members),
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1,
                         "url": f"{BASE}/{OUT_DIR}/{slugmap[m['name']]}", "name": m["name"]}
                        for i, m in enumerate(members)
                    ],
                },
            }, ensure_ascii=False)
            empty_note = (
                '<p class="empty-note" style="font-size:13px;font-style:italic;color:#5c4a2a">'
                'No legends have been dated to this period yet — check back as the archive grows.</p>'
            ) if not members else ""
            page = build_browse_page(
                page_title=f"{p['title']} Folklore — Folklore Finder",
                desc=short_desc(p["overview"], 155),
                url=url,
                h1=p["title"],
                intro=p["overview"],
                crumb=p["title"],
                nav_html=nav_links(period_nav_items, slug),
                cards_html=cards or empty_note,
                jsonld=period_jsonld,
                nav_active="periods",
                wrap_class="ornamented",
                track_script=track_event_script("period_viewed", period_slug=slug),
            )
            with io.open(os.path.join(period_dir, f"{slug}.html"), "w", encoding="utf-8") as f:
                f.write(page)
            browse_urls.append(url)
            timeline_cards.append(
                f'<a class="b-card" href="{url}">'
                f'<span class="b-name">{esc(p["title"])}</span>'
                f'<span class="b-region">{len(members)} legend{"s" if len(members) != 1 else ""}</span>'
                f'<span class="b-summary">{esc(short_desc(p["overview"], 140))}</span></a>'
            )

        timeline_url = f"{BASE}/{OUT_DIR}/periods"
        timeline_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "Explore Through Time",
            "description": "Browse British and Irish folklore by historical period, from prehistoric "
                           "Britain to modern folklore.",
            "url": timeline_url,
            "isPartOf": {"@type": "WebSite", "name": "Folklore Finder", "url": BASE + "/"},
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": len(periods),
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "url": period_page_url(p["slug"]), "name": p["title"]}
                    for i, p in enumerate(periods)
                ],
            },
        }, ensure_ascii=False)
        timeline_page = build_browse_page(
            page_title="Explore Through Time — Folklore Finder",
            desc="Browse British and Irish folklore by historical period, from prehistoric Britain "
                 "to modern folklore.",
            url=timeline_url,
            h1="Explore Through Time",
            intro="From the standing stones of prehistoric Britain to the urban legends of the present day — "
                  "browse the archive by the historical period each legend is associated with.",
            crumb="Explore Through Time",
            nav_html="",
            cards_html="\n".join(timeline_cards),
            jsonld=timeline_jsonld,
            nav_active="periods",
            wrap_class="ornamented",
        )
        with io.open(os.path.join(OUT_DIR, "periods.html"), "w", encoding="utf-8") as f:
            f.write(timeline_page)
        browse_urls.append(timeline_url)

    # Browse sections for the A-Z index page
    cat_links = "".join(
        '<a href="' + f"{BASE}/{OUT_DIR}/category/{c}" + '">'
        '<span class="c-dot" style="background:' + esc(meta.get(c, {}).get("colour", "#8b3a1a")) + '"></span>'
        + esc(cats.get(c, c)) + ' <span class="c-count">' + str(len(cat_groups[c])) + '</span></a>'
        for c in cat_order
    )
    region_links = "".join(
        '<a href="' + f"{BASE}/{OUT_DIR}/region/{t}" + '">'
        + esc(prettify_region(t)) + ' <span class="c-count">' + str(len(region_groups[t])) + '</span></a>'
        for t in region_order
    )
    collection_links = "".join(
        '<a href="' + f"{BASE}/{OUT_DIR}/collection/{slug}" + '">'
        + esc(title) + ' <span class="c-count">' + str(count) + '</span></a>'
        for slug, title, count in built_collections
    )
    collection_sec = (
        ('<div class="browse-sec"><div class="region-links">'
         + collection_links + '</div></div>') if built_collections else ''
    )
    period_links = "".join(
        '<a href="' + period_page_url(p["slug"]) + '">'
        + esc(p["title"]) + ' <span class="c-count">' + str(len(period_members[p["slug"]])) + '</span></a>'
        for p in periods
    )
    period_sec = (
        ('<div class="browse-sec"><div class="region-links">'
         + period_links + '</div></div>') if periods else ''
    )
    place_explorer = '''
<section class="place-explorer" aria-labelledby="place-explorer-title">
  <div class="place-map-wrap">
    <svg class="place-map" viewBox="0 0 400 500" role="img" aria-labelledby="place-map-title place-map-desc">
      <title id="place-map-title">Explore folklore by place</title>
      <desc id="place-map-desc">Choose England, Scotland, Wales, Ireland or Northern Ireland to see its legends on the map.</desc>
      <a class="place-shape" href="/map?region=ireland" aria-label="Explore legends in Ireland"><title>Ireland</title><use href="/region-map.svg#region-ireland"></use></a>
      <a class="place-shape" href="/map?region=northern-ireland" aria-label="Explore legends in Northern Ireland"><title>Northern Ireland</title><use href="/region-map.svg#region-northern-ireland"></use></a>
      <a class="place-shape" href="/map?region=england" aria-label="Explore legends in England"><title>England</title><use href="/region-map.svg#region-england"></use></a>
      <a class="place-shape" href="/map?region=wales" aria-label="Explore legends in Wales"><title>Wales</title><use href="/region-map.svg#region-wales"></use></a>
      <a class="place-shape" href="/map?region=scotland" aria-label="Explore legends in Scotland"><title>Scotland</title><use href="/region-map.svg#region-scotland"></use></a>
    </svg>
  </div>
  <div class="place-copy">
    <p class="place-kicker">Across the islands</p>
    <h2 id="place-explorer-title">Explore by place</h2>
    <p>Follow the stories of a particular country onto the map, or browse the regional index below.</p>
    <nav class="place-links" aria-label="Explore folklore by country">
      <a href="/map?region=england">England</a><a href="/map?region=scotland">Scotland</a><a href="/map?region=wales">Wales</a><a href="/map?region=ireland">Ireland</a><a href="/map?region=northern-ireland">Northern Ireland</a>
    </nav>
  </div>
</section>'''
    browse_tab_defs = [
        ("category", "By Category", '<div class="browse-sec"><div class="cat-links">' + cat_links + '</div></div>'),
        ("region", "By Region", '<div class="browse-sec"><div class="region-links">' + region_links + '</div></div>'),
        ("period", "By Period", period_sec),
        ("collection", "By Collection", collection_sec),
    ]
    browse_tab_buttons = "".join(
        f'<button type="button" class="browse-tab{" active" if i == 0 else ""}" data-tab="{key}">{esc(label)}</button>'
        for i, (key, label, _) in enumerate(browse_tab_defs) if _
    )
    browse_tab_panels = "".join(
        f'<div class="browse-tab-panel{" active" if i == 0 else ""}" data-tab-panel="{key}">{panel}</div>'
        for i, (key, _, panel) in enumerate(browse_tab_defs) if panel
    )
    browse_sections = (
        place_explorer
        + '<div class="browse-tabs" role="tablist" aria-label="Browse legends by">' + browse_tab_buttons + '</div>'
        + '<div class="browse-tab-panels">' + browse_tab_panels + '</div>'
        + '<script>(function(){'
          'var tabs=document.querySelectorAll(".browse-tab");'
          'var panels=document.querySelectorAll(".browse-tab-panel");'
          'tabs.forEach(function(t){t.addEventListener("click",function(){'
          'tabs.forEach(function(o){o.classList.remove("active")});'
          'panels.forEach(function(p){p.classList.remove("active")});'
          't.classList.add("active");'
          'document.querySelector(\'.browse-tab-panel[data-tab-panel="\'+t.dataset.tab+\'"]\').classList.add("active");'
          '});});'
          '})();</script>'
        '<h2 class="azh">A&#8211;Z</h2>'
    )

    # A-Z index page — grouped by first letter with letter headings
    az_groups = {}
    az_order = []
    for l in legends:  # already sorted by name.lower()
        ch = l["name"].lstrip()[:1].upper()
        if not ch.isalpha():
            ch = "#"
        if ch not in az_groups:
            az_groups[ch] = []
            az_order.append(ch)
        az_groups[ch].append(l)
    az_parts = []
    for letter in az_order:
        lis = "".join(
            f'<li><a href="{BASE}/{OUT_DIR}/{slugmap[x["name"]]}">{esc(x["name"])}</a>'
            f'<span>{esc(x.get("region",""))}</span></li>'
            for x in az_groups[letter]
        )
        az_parts.append(f'<h3 class="az-letter" id="az-{letter}">{letter}</h3><ul>{lis}</ul>')
    az_content = "\n".join(az_parts)
    index_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<script>if(location.hostname.indexOf("pages.dev")>-1){{location.replace("https://folklorefinder.uk"+location.pathname+location.search+location.hash);}}</script>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "64d1fd37251d426f8a0d8fbc83ea350b"}}'></script>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>All Legends &#8212; Folklore Finder</title>
<meta name="description" content="Browse all {written} myths, legends, ghosts and folklore stories from Britain and Ireland, each pinned to its place of origin on the map."/>
<link rel="canonical" href="{BASE}/{OUT_DIR}/"/>
<link rel="icon" type="image/png" href="{BASE}/favicon.png"/>
<meta property="og:type" content="website"/>
<meta property="og:title" content="All Legends &#8212; Folklore Finder"/>
<meta property="og:description" content="Browse all {written} myths, legends, ghosts and folklore stories from every region of Britain and Ireland, each pinned to its place of origin on our interactive folklore map."/>
<meta property="og:url" content="{BASE}/{OUT_DIR}/"/>
<meta property="og:image" content="{BASE}/og/preview-folklore-finder.jpg"/>
<meta property="og:site_name" content="Folklore Finder"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="All Legends &#8212; Folklore Finder"/>
<meta name="twitter:description" content="Browse all {written} myths, legends, ghosts and folklore stories from every region of Britain and Ireland, each pinned to its place of origin on our interactive folklore map."/>
<meta name="twitter:image" content="{BASE}/og/preview-folklore-finder.jpg"/>
<link rel="stylesheet" href="/fonts/fonts.css"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:radial-gradient(circle at 12% 8%,rgba(176,144,96,.1),transparent 25rem),linear-gradient(180deg,#e8dcc5,#f6f1e6 34rem,#eadfc9);color:#3f3023;font-family:'Spectral',serif;min-height:100vh}}
.wrap{{width:min(1600px,calc(100% - 56px));max-width:none;margin:0 auto;padding:30px 0 68px}}
h1{{font-family:'Marcellus',serif;font-size:clamp(30px,3vw,44px);font-weight:400;margin-bottom:6px;color:#3f3023;line-height:1.12}}
h1::after{{content:"";display:block;width:132px;height:40px;margin:9px 0 19px;background:url('/assets/ornaments/generated-variants/oak-divider-horizontal.webp') left center/contain no-repeat;opacity:.55}}
.az{{column-count:10;column-gap:24px}}
@media(max-width:1450px){{.az{{column-count:8}}}}
@media(max-width:1100px){{.az{{column-count:6}}}}
@media(max-width:880px){{.az{{column-count:4}}}}
@media(max-width:680px){{.az{{column-count:3}}}}
@media(max-width:520px){{.az{{column-count:2}}}}
@media(max-width:380px){{.az{{column-count:1}}}}
.az-letter{{font-family:'Marcellus',serif;font-size:17px;color:#8b3a1a;margin:0 0 7px;padding-bottom:3px;border-bottom:1px solid #b09060;break-after:avoid;break-inside:avoid}}
.az ul{{list-style:none;margin:0 0 16px}}
.az li{{break-inside:avoid;padding:5px 0;border-bottom:.5px solid rgba(176,144,96,.3)}}
.az li a{{color:#8b3a1a;text-decoration:none;font-size:15px}}
.az li span{{display:block;font-size:11.5px;font-style:italic;color:#5c4a2a}}
.browse-tabs{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px;border-bottom:1px solid rgba(90,70,50,.28);padding-bottom:0}}
.browse-tab{{font-family:'Marcellus',serif;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#5a4632;background:none;border:none;border-bottom:3px solid transparent;padding:10px 6px 12px;cursor:pointer;transition:color .15s,border-color .15s}}
.browse-tab:hover{{color:#3f3023}}
.browse-tab.active{{color:#8b3a1a;border-bottom-color:#8b3a1a}}
.browse-tab-panels{{margin:0 0 44px}}
.browse-tab-panel{{display:none}}
.browse-tab-panel.active{{display:block}}
.browse-sec{{margin:0;padding:22px 0 0}}
.browse-sec h2,.azh{{font-family:'Marcellus',serif;font-size:19px;font-weight:400;margin-bottom:15px;color:#3f3023}}
.azh{{margin:0 0 20px;padding-top:24px;border-top:1px solid rgba(90,70,50,.28)}}
.cat-links,.region-links{{display:flex;flex-wrap:wrap;gap:9px}}
.cat-links a,.region-links a{{display:inline-flex;align-items:center;gap:7px;font-family:'Marcellus',serif;font-size:13px;color:#3f3023;background:rgba(246,241,230,.72);border:1px solid rgba(90,70,50,.32);border-radius:0;padding:7px 13px;text-decoration:none;box-shadow:inset 0 0 0 3px rgba(255,255,255,.12)}}
.cat-links a:hover,.region-links a:hover{{border-color:#c4622a}}
.c-count{{font-size:11px;color:#5c4a2a;font-style:italic}}
.c-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;flex-shrink:0}}
.place-explorer{{position:relative;isolation:isolate;display:grid;grid-template-columns:minmax(320px,520px) minmax(0,1fr);align-items:center;gap:clamp(42px,7vw,110px);margin:48px 42px 82px;padding:58px 70px;border:0;background:rgba(246,241,230,.68);box-shadow:0 16px 40px rgba(63,48,35,.08)}}
.place-explorer::after{{content:"";position:absolute;inset:-31px;z-index:2;box-sizing:border-box;border:38px solid transparent;border-image:url('/assets/ornaments/generated-variants/oak-branch-frame-v1.png?v=20260713c') 230 / 38px / 0 round;filter:saturate(.62) brightness(.9) contrast(.9) drop-shadow(0 4px 5px rgba(63,48,35,.2));pointer-events:none}}
.place-explorer>*{{position:relative;z-index:1}}
.place-map-wrap{{display:flex;justify-content:center;background:radial-gradient(circle,rgba(176,144,96,.15),transparent 68%)}}
.place-map{{display:block;width:min(100%,430px);height:auto;overflow:visible}}
.place-shape use{{fill:rgba(102,115,90,.2);stroke:#5a4632;stroke-width:1.7;vector-effect:non-scaling-stroke;transition:fill .18s,stroke .18s}}
.place-shape:hover use,.place-shape:focus use{{fill:#c4622a;stroke:#3f3023}}
.place-copy{{position:relative}}
.place-kicker{{margin:0;color:#66735a;font-family:'Marcellus',serif;font-size:10px;letter-spacing:.16em;text-transform:uppercase}}
.place-kicker::after{{content:'';display:block;width:150px;height:42px;margin:9px 0 12px;background:url('/assets/ornaments/generated-variants/oak-divider-horizontal.webp') left center/contain no-repeat;opacity:.58}}
.place-copy h2{{font-family:'Marcellus',serif;font-size:clamp(24px,4vw,36px);font-weight:400;margin-bottom:9px;color:#3f3023}}
.place-copy p:not(.place-kicker){{max-width:520px;margin-bottom:20px;color:#5a4632;font-size:16px;line-height:1.55}}
.place-links{{display:flex;flex-wrap:wrap;gap:8px}}
.place-links a{{padding:7px 12px;border:1px solid rgba(90,70,50,.35);color:#3f3023;text-decoration:none;font-family:'Marcellus',serif;font-size:12px}}
.place-links a:hover{{border-color:#c4622a;color:#9d461f}}
@media(max-width:1000px){{.browse-link-sections{{grid-template-columns:1fr 1fr}}.browse-link-sections .browse-sec:last-child{{grid-column:1/-1}}}}
@media(max-width:760px){{.wrap{{width:calc(100% - 32px)}}.place-explorer{{grid-template-columns:1fr;margin:42px 24px 68px;padding:44px 34px;gap:22px}}.place-explorer::after{{inset:-19px;border-width:24px;border-image-width:24px}}.place-map{{width:min(100%,280px)}}.browse-link-sections{{grid-template-columns:1fr;gap:18px}}.browse-link-sections .browse-sec:last-child{{grid-column:auto}}}}
@media(max-width:480px){{.browse-link-sections .browse-sec:last-child .region-links{{grid-template-columns:1fr}}}}
{TOPNAV_CSS}
</style></head>
<body>
{topnav_html("browse")}
<div class="wrap"><h1>All Legends ({written})</h1>{browse_sections}<div class="az">
{az_content}
</div></div>
{footer_html()}
</body></html>"""
    with io.open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # sitemap.xml — legend pages carry their own date_modified as lastmod, so the
    # signal is honest; app/aggregation pages use the build date.
    urls = [f"{BASE}/", f"{BASE}/map", f"{BASE}/{OUT_DIR}/", f"{BASE}/achievements", f"{BASE}/about", f"{BASE}/editorial", f"{BASE}/updates", f"{BASE}/privacy", f"{BASE}/feed.xml"]
    urls += browse_urls
    urls += [f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}" for l in legends]
    lastmod_map = {f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}": (l.get("date_modified") or today)
                   for l in legends}
    sitemap_images = {}
    for l in legends:
        featured = featured_pages.get(l["name"], {})
        image_path = featured.get("image", "")
        if image_path:
            sitemap_images[f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}"] = {
                "loc": absolute_asset_url(image_path),
                "title": featured.get("alt") or f"{l['name']} hero artwork",
                "caption": featured.get("caption", ""),
            }
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for i, u in enumerate(urls):
        pr = "1.0" if i == 0 else ("0.8" if i == 1 else "0.6")
        lm = lastmod_map.get(u, today)
        img = sitemap_images.get(u)
        if img:
            image_bits = [
                f"    <image:loc>{esc(img['loc'])}</image:loc>",
                f"    <image:title>{esc(img['title'])}</image:title>",
            ]
            if img.get("caption"):
                image_bits.append(f"    <image:caption>{esc(img['caption'])}</image:caption>")
            sm.append(
                f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod><priority>{pr}</priority>\n"
                "  <image:image>\n" + "\n".join(image_bits) + "\n  </image:image></url>"
            )
        else:
            sm.append(f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod><priority>{pr}</priority></url>")
    sm.append("</urlset>")
    with io.open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")

    # feed.xml — RSS feed of the most recently added legends
    recent = sorted(
        (l for l in legends if l.get("date_added")),
        key=lambda l: l["date_added"], reverse=True,
    )[:30]
    now_rfc822 = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    items = []
    for l in recent:
        url = f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}"
        cat = cats.get(l.get("category", ""), l.get("category", ""))
        pub = datetime.datetime.strptime(l["date_added"], "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc).strftime("%a, %d %b %Y 12:00:00 GMT")
        items.append(
            "  <item>\n"
            f"    <title>{esc(l['name'])}</title>\n"
            f"    <link>{url}</link>\n"
            f"    <guid isPermaLink=\"true\">{url}</guid>\n"
            f"    <pubDate>{pub}</pubDate>\n"
            f"    <category>{esc(cat)}</category>\n"
            f"    <description>{esc(short_desc(l.get('summary', '')))}</description>\n"
            "  </item>"
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        '  <title>Folklore Finder — New Legends</title>\n'
        f'  <link>{BASE}/</link>\n'
        '  <description>Recently added myths, legends, ghosts and folklore from across Britain and Ireland.</description>\n'
        '  <language>en-gb</language>\n'
        f'  <lastBuildDate>{now_rfc822}</lastBuildDate>\n'
        f'  <atom:link xmlns:atom="http://www.w3.org/2005/Atom" href="{BASE}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items) + "\n"
        '</channel></rss>\n'
    )
    with io.open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)

    # legend-images/manifest.json — slugs that have a hero image, so the
    # homepage's Legend of the Week can prefer entries with artwork.
    imaged = sorted(
        os.path.basename(p)[:-len("-hero.jpg")]
        for p in glob.glob(os.path.join("legend-images", "*-hero.jpg"))
    )
    with io.open(os.path.join("legend-images", "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(imaged, f, ensure_ascii=False)

    # updates.html — Recently Added Legends / New Collections cards
    update_whats_new_page(recent, built_collections, slugmap, cats, meta)

    print(f"Generated {written} legend pages + index + sitemap ({len(urls)} URLs) + feed.xml ({len(recent)} items) + image manifest ({len(imaged)})")


if __name__ == "__main__":
    build()
