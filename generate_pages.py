# -*- coding: utf-8 -*-
"""
generate_pages.py — emit static, SEO-indexable HTML pages, one per legend,
plus an A-Z index page and a full sitemap.xml.

These pages are served by Cloudflare Pages independently of the main map app.
A visitor only ever loads one of them at a time (arriving from search or a
shared link); the interactive map (map.html) is unaffected.

Run after legends.json changes:  python generate_pages.py
"""
import json, io, os, re, unicodedata, html, urllib.parse, datetime, math, hashlib
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


# ── Browse-by-category / browse-by-region support ──────────────────────────
NATIONS = ["england", "scotland", "wales", "ireland", "northern-ireland", "isle-of-man", "channel-islands"]

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
    return ('<header class="site-banner"><a class="banner-link" href="' + BASE + '/">'
            '<img src="' + BASE + '/green-man.png" class="banner-emblem" alt=""/>'
            '<span class="banner-text"><span class="banner-title"><i>&#10022;</i> '
            'Folklore Map of Britain &amp; Ireland <i>&#10022;</i></span>'
            '<span class="banner-sub">Myths, Legends &amp; Spectral Encounters</span>'
            '</span></a></header>')


# Site-wide top navigation (shown on every page except the interactive map).
TOPNAV_CSS = (
    ".topnav{display:flex;align-items:center;justify-content:center;gap:4px;"
    "background:#1a0e06;padding:11px 16px;border-bottom:1px solid rgba(176,144,96,0.2);flex-wrap:wrap}"
    ".topnav a{font-family:'Marcellus',serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;"
    "color:rgba(242,232,213,0.78);text-decoration:none;padding:6px 14px;border-radius:3px;"
    "transition:background .15s,color .15s}"
    ".topnav a:hover{color:#f2e8d5;background:rgba(196,98,42,0.18)}"
    ".topnav a.active{color:#c4622a}"
)

TOPNAV_ITEMS = [
    ("home", "Home", "/"),
    ("map", "Map", "/map"),
    ("browse", "Browse", "/" + OUT_DIR + "/"),
    ("collections", "Collections", "/" + OUT_DIR + "/collections"),
    ("about", "About", "/about"),
    ("updates", "Updates", "/updates"),
]


def topnav_html(active=""):
    parts = ['<nav class="topnav">']
    for key, label, path in TOPNAV_ITEMS:
        cls = ' class="active"' if key == active else ''
        parts.append(f'<a href="{BASE}{path}"{cls}>{label}</a>')
    parts.append('</nav>')
    return "".join(parts)


def footer_html():
    return ('<footer style="text-align:center;padding:30px 20px;font-size:12px;color:#5c4a2a">'
            'Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; '
            '<a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener" style="color:#5c4a2a">&#9749; Ko-fi</a> &#183; '
            '<a href="' + BASE + '/privacy" style="color:#5c4a2a">Privacy</a></footer>')


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


BROWSE_STYLE = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#e0d0b0;color:#2c1f0e;font-family:'Spectral',serif;line-height:1.7;min-height:100vh}
.site-banner{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#3d2510 0%,#1a0e06 45%,#2c1f0e 100%);padding:16px 20px;text-align:center}
.site-banner::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}
.site-banner::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}
.banner-link{display:inline-flex;align-items:center;gap:13px;text-decoration:none}
.banner-emblem{width:48px;height:48px;object-fit:contain;flex-shrink:0}
.banner-text{display:flex;flex-direction:column;align-items:center;line-height:1.15}
.banner-title{font-family:'Marcellus',serif;font-size:21px;font-weight:400;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}
.banner-title i{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}
.banner-sub{font-family:'Spectral',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}
@media(max-width:560px){.banner-title{font-size:15px}.banner-emblem{width:38px;height:38px}.banner-sub{font-size:11px}}
.wrap{max-width:760px;margin:0 auto;padding:24px 20px 60px}
.crumb{font-size:12px;color:#5c4a2a;margin-bottom:14px}
.crumb a{color:#8b3a1a;text-decoration:none}
.browse-h1{font-family:'Marcellus',serif;font-size:27px;margin-bottom:6px;color:#2c1f0e;line-height:1.15}
.browse-intro{font-size:16px;color:#5c4a2a;margin-bottom:16px}
.browse-nav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.browse-nav a{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#8b3a1a;border:1px solid #b09060;border-radius:3px;padding:5px 11px;text-decoration:none}
.browse-nav a:hover,.browse-nav a.active{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}
.browse-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.b-card{background:#f2e8d5;border:1px solid #b09060;border-radius:5px;padding:14px 15px;text-decoration:none;color:#2c1f0e;transition:border-color .15s,transform .1s}
.b-card:hover{border-color:#c4622a;transform:translateY(-2px)}
.b-card span{display:block}
.b-cat{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#8b3a1a;padding:2px 8px;border-radius:3px;margin-bottom:8px;width:max-content;max-width:100%}
.b-name{font-family:'Marcellus',serif;font-size:15px;line-height:1.25;margin-bottom:4px}
.b-region{font-style:italic;font-size:12px;color:#5c4a2a}
.b-summary{font-size:13.5px;color:#3a2c14;margin-top:8px;line-height:1.5}
.back{display:inline-block;margin-top:24px;font-size:13px;color:#5c4a2a}
.pagination{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:7px;margin-top:30px}
.pagination a,.pagination span{font-family:'Marcellus',serif;font-size:13px;min-width:34px;text-align:center;padding:6px 10px;border:1px solid #b09060;border-radius:3px;text-decoration:none;color:#8b3a1a}
.pagination a:hover{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}
.pagination .current{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}
.pagination .disabled{color:#b09060;border-color:#d8c8a8;cursor:default}
.pagination .gap{border:none;color:#5c4a2a;min-width:auto;padding:6px 2px}
@media(max-width:560px){.browse-grid{grid-template-columns:1fr 1fr}}
@media(max-width:380px){.browse-grid{grid-template-columns:1fr}}
"""


def build_browse_page(page_title, desc, url, h1, intro, crumb, nav_html, cards_html,
                      ogimage=None, jsonld=None, head_extra="", after_grid="", nav_active="browse"):
    jsonld_html = ('<script type="application/ld+json">' + jsonld + '</script>\n') if jsonld else ''
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
            '<meta property="og:image" content="' + (ogimage or (BASE + '/og/preview.png')) + '"/>\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link href="https://fonts.googleapis.com/css2?family=Marcellus&family=Spectral:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">\n'
            + jsonld_html + head_extra
            + '<style>' + BROWSE_STYLE + TOPNAV_CSS + '</style></head>\n<body>\n'
            + topnav_html(nav_active) + '\n' + banner_html() + '\n<div class="wrap">\n'
            '<nav class="crumb"><a href="' + BASE + '/">Home</a> &#8250; '
            '<a href="' + BASE + '/' + OUT_DIR + '/">All legends</a> &#8250; '
            '<span>' + esc(crumb) + '</span></nav>\n'
            '<h1 class="browse-h1">' + esc(h1) + '</h1>\n'
            '<p class="browse-intro">' + esc(intro) + '</p>\n'
            + nav_html + '\n<div class="browse-grid">\n' + cards_html
            + '\n</div>\n' + after_grid
            + '<a class="back" href="' + BASE + '/' + OUT_DIR + '/">&#8592; Browse all legends</a>\n'
            '</div>\n' + footer_html() + '\n</body></html>')


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


def host_of(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "") or "source"
    except Exception:
        return "source"


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
    "folklorethursday.com": "secondary",
    "transceltic.com": "secondary",
    "mysteriousbritain.co.uk": "secondary",
    "historic-uk.com": "secondary",
}
TIER_LABELS = {
    "primary": "primary record",
    "heritage": "heritage record",
    "secondary": "secondary source",
    "encyclopedic": "encyclopedic",
    "popular": "popular source",
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


LEGACY_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<script>if(location.hostname.indexOf("pages.dev")>-1){{location.replace("https://folklorefinder.uk"+location.pathname+location.search+location.hash);}}</script>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "64d1fd37251d426f8a0d8fbc83ea350b"}}'></script>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<meta name="description" content="{desc}"/>
<link rel="canonical" href="{url}"/>
<link rel="icon" type="image/png" href="{base}/favicon.png"/>
<meta property="og:type" content="article"/>
<meta property="og:url" content="{url}"/>
<meta property="og:title" content="{ogtitle}"/>
<meta property="og:description" content="{desc}"/>
<meta property="og:image" content="{ogimage}"/>
<meta property="og:site_name" content="Folklore Map of Britain &amp; Ireland"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{ogtitle}"/>
<meta name="twitter:description" content="{desc}"/>
<meta name="twitter:image" content="{ogimage}"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Marcellus&family=Spectral:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<script type="application/ld+json">{jsonld}</script>
{breadcrumb_jsonld}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e0d0b0;color:#2c1f0e;font-family:'Spectral',serif;line-height:1.7;min-height:100vh}}
.site-banner{{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#3d2510 0%,#1a0e06 45%,#2c1f0e 100%);padding:16px 20px;text-align:center}}
.site-banner::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}}
.site-banner::after{{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}}
.banner-link{{display:inline-flex;align-items:center;gap:13px;text-decoration:none}}
.banner-emblem{{width:48px;height:48px;object-fit:contain;flex-shrink:0}}
.banner-text{{display:flex;flex-direction:column;align-items:center;line-height:1.15}}
.banner-title{{font-family:'Marcellus',serif;font-size:21px;font-weight:400;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}}
.banner-title i{{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}}
.banner-sub{{font-family:'Spectral',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}}
.watermark{{position:absolute;top:26px;right:24px;width:88px;height:88px;color:#8b3a1a;opacity:.1;pointer-events:none;z-index:0}}
@media(max-width:560px){{.banner-title{{font-size:15px}}.banner-emblem{{width:38px;height:38px}}.banner-sub{{font-size:11px}}}}
.wrap{{max-width:680px;margin:0 auto;padding:11px 20px 60px}}
.card{{position:relative;overflow:hidden;background:#f2e8d5;border:1px solid #b09060;border-radius:6px;margin-top:30px;padding:32px;box-shadow:0 4px 20px rgba(44,31,14,.18)}}
.card>*:not(.watermark){{position:relative;z-index:1}}
.card>.watermark{{position:absolute;top:26px;right:24px;width:88px;height:88px;z-index:0}}
.cat{{font-family:'Marcellus',serif;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#fff;background:#8b3a1a;display:inline-block;padding:3px 10px;border-radius:2px}}
h1{{font-family:'Marcellus',serif;font-size:30px;margin:14px 0 4px;color:#2c1f0e;line-height:1.15}}
.region{{font-style:italic;color:#5c4a2a;margin-bottom:18px}}
.crumb{{font-size:12.5px;color:#5c4a2a;margin-bottom:16px;line-height:1.5}}
.crumb a{{color:#8b3a1a;text-decoration:none}}
.crumb a:hover{{text-decoration:underline}}
.crumb .sep{{color:#b09060;margin:0 6px}}
.crumb .here{{color:#5c4a2a}}
.summary{{font-size:17px}}
.summary-cont{{font-size:17px;margin-top:14px}}
.cta{{display:inline-block;margin-top:26px;background:#2c1f0e;color:#f2e8d5;font-family:'Marcellus',serif;font-size:13px;letter-spacing:.08em;text-transform:uppercase;padding:12px 22px;border-radius:3px;text-decoration:none}}
.cta:hover{{background:#8b3a1a}}
.share-row{{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}}
.share-btn{{font-family:'Marcellus',serif;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#8b3a1a;background:transparent;border:1px solid #b09060;border-radius:3px;padding:9px 16px;cursor:pointer;transition:background .15s,color .15s,border-color .15s}}
.share-btn:hover{{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}}
.share-status{{position:absolute !important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
.src{{display:block;margin-top:18px;font-size:13px;font-style:italic;color:#5c4a2a}}
.src-tier{{color:#7a6a4a}}
.sources{{margin-top:18px;font-size:13px;color:#5c4a2a}}
.sources-head{{font-style:italic}}
.sources ul{{list-style:none;margin:5px 0 0;padding:0}}
.sources li{{margin:3px 0}}
.sources a{{color:#8b3a1a}}
.src a{{color:#8b3a1a}}
.back{{display:inline-block;margin-top:22px;font-size:13px;color:#5c4a2a}}
.related{{margin-top:36px}}
.related-head{{font-family:'Marcellus',serif;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#8b3a1a;display:flex;align-items:center;gap:12px;margin-bottom:16px}}
.related-head::before,.related-head::after{{content:'';flex:1;height:1px;background:linear-gradient(90deg,transparent,#b09060)}}
.related-head::after{{background:linear-gradient(90deg,#b09060,transparent)}}
.carousel{{position:relative}}
.carousel-track{{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;scroll-behavior:smooth;padding-bottom:8px;-webkit-overflow-scrolling:touch}}
.carousel-track::-webkit-scrollbar{{height:6px}}
.carousel-track::-webkit-scrollbar-track{{background:rgba(176,144,96,.15);border-radius:3px}}
.carousel-track::-webkit-scrollbar-thumb{{background:rgba(139,58,26,.4);border-radius:3px}}
.rel-card{{flex:0 0 198px;scroll-snap-align:start;background:#f2e8d5;border:1px solid #b09060;border-radius:5px;padding:14px 15px;text-decoration:none;color:#2c1f0e;transition:border-color .15s,transform .1s}}
.rel-card:hover{{border-color:#c4622a;transform:translateY(-2px)}}
.rel-card span{{display:block}}
.rel-cat{{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#8b3a1a;padding:2px 8px;border-radius:3px;margin-bottom:8px;width:max-content;max-width:100%}}
.rel-name{{font-family:'Marcellus',serif;font-size:15px;line-height:1.25;margin-bottom:4px}}
.rel-region{{font-style:italic;font-size:12px;color:#5c4a2a}}
.carousel-btn{{position:absolute;top:42%;transform:translateY(-50%);width:34px;height:34px;border-radius:50%;border:1px solid #b09060;background:#f2e8d5;color:#8b3a1a;font-family:'Marcellus',serif;font-size:18px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;box-shadow:0 2px 8px rgba(44,31,14,.25)}}
.carousel-btn:hover{{background:#8b3a1a;color:#f2e8d5}}
.carousel-btn.prev{{left:-10px}}
.carousel-btn.next{{right:-10px}}
@media(max-width:560px){{.carousel-btn{{display:none}}.rel-card{{flex-basis:170px}}}}
footer{{text-align:center;padding:30px 20px;font-size:12px;color:#5c4a2a}}
{topnav_css}
</style>
</head>
<body>
{topnav}
<header class="site-banner"><a class="banner-link" href="{base}/"><img src="{base}/green-man.png" class="banner-emblem" alt=""/><span class="banner-text"><span class="banner-title"><i>&#10022;</i> Folklore Map of Britain &amp; Ireland <i>&#10022;</i></span><span class="banner-sub">Myths, Legends &amp; Spectral Encounters</span></span></a></header>
<div class="wrap">
{breadcrumb}
<article class="card">
<span class="cat" style="background:{catcolour}">{catname}</span>
<h1>{name}</h1>
<div class="region">{region}</div>
{body}
<a class="cta" href="{maplink}">Explore on the interactive map &#8594;</a>
{sources}
<div class="share-row" role="group" aria-label="Share this legend">
<button type="button" class="share-btn" id="copyLinkBtn">Copy link</button>
<button type="button" class="share-btn" id="webShareBtn" hidden>Share&#8230;</button>
</div>
<span class="share-status" id="shareStatus" role="status" aria-live="polite"></span>
<svg class="watermark" viewBox="0 0 512 512" aria-hidden="true"><path d="{watermark}" fill="currentColor"/></svg>
</article>
{related}
<a class="back" href="{base}/legends/">&#8592; Browse all legends</a>
</div>
<footer>Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; <a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener" style="color:#5c4a2a">&#9749; Ko-fi</a> &#183; <a href="{base}/privacy" style="color:#5c4a2a">Privacy</a></footer>
<script>
document.querySelectorAll('.carousel').forEach(function(c){{
  var t=c.querySelector('.carousel-track');
  var p=c.querySelector('.prev'), n=c.querySelector('.next');
  if(p)p.addEventListener('click',function(){{t.scrollBy({{left:-220,behavior:'smooth'}});}});
  if(n)n.addEventListener('click',function(){{t.scrollBy({{left:220,behavior:'smooth'}});}});
}});
(function(){{
  var link=document.querySelector('link[rel=canonical]');
  var url=(link&&link.href)||location.href;
  var status=document.getElementById('shareStatus');
  var copyBtn=document.getElementById('copyLinkBtn');
  var revertTimer=null;
  function announce(m){{ if(status) status.textContent=m; }}
  function markCopied(){{
    announce('Link copied');           // for screen readers (visually hidden)
    if(copyBtn){{
      copyBtn.textContent='Copied';
      clearTimeout(revertTimer);
      revertTimer=setTimeout(function(){{ copyBtn.textContent='Copy link'; }},2000);
    }}
  }}
  function fallbackCopy(){{
    try{{
      var ta=document.createElement('textarea');
      ta.value=url; ta.setAttribute('readonly','');
      ta.style.position='absolute'; ta.style.left='-9999px';
      document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); document.body.removeChild(ta);
      markCopied();
    }}catch(e){{ announce("Couldn't copy. Press Ctrl+C to copy the address."); }}
  }}
  if(copyBtn) copyBtn.addEventListener('click',function(){{
    if(navigator.clipboard&&navigator.clipboard.writeText){{
      navigator.clipboard.writeText(url).then(markCopied,fallbackCopy);
    }} else {{ fallbackCopy(); }}
  }});
  var shareBtn=document.getElementById('webShareBtn');
  if(shareBtn&&navigator.share){{
    shareBtn.hidden=false;
    shareBtn.addEventListener('click',function(){{
      navigator.share({{title:document.title,url:url}}).catch(function(){{}});
    }});
  }}
}})();
</script>
</body>
</html>
"""


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
<meta property="og:site_name" content="Folklore Map of Britain &amp; Ireland"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="$ogtitle"/>
<meta name="twitter:description" content="$desc"/>
<meta name="twitter:image" content="$ogimage"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Marcellus&amp;family=Spectral:ital,wght@0,400;0,500;0,600;1,400;1,500&amp;display=swap" rel="stylesheet"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H" crossorigin="anonymous"/>
<link rel="stylesheet" href="$base/legend-page.css"/>
<script type="application/ld+json">$jsonld</script>
$breadcrumb_jsonld
</head>
<body>
$topnav
<header class="brandbar">
  <a class="brand" href="$base/">
    <img src="$base/green-man.png" alt=""/>
    <span>
      <span class="brand-name">Folklore Map of Britain &amp; Ireland</span>
      <span class="brand-line">Myths, Legends &amp; Spectral Encounters</span>
    </span>
  </a>
</header>
<main>
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
        <p class="standfirst">$standfirst</p>
      </div>
$hero_caption
    </section>

    <div class="content-grid">
      <article class="article">
        <div class="article-label">The legend</div>
        $featured_body
        <div class="article-actions" aria-label="Legend actions">
          <a class="button" href="$maplink">Open on full map</a>
          <button class="button secondary" id="copyLinkBtn" type="button">Copy link</button>
          <button class="button secondary" id="webShareBtn" type="button" hidden>Share</button>
        </div>
        <span class="share-status" id="shareStatus" role="status" aria-live="polite"></span>
      </article>

      <aside class="sidebar" aria-label="Legend details">
        <section class="side-card">
          <div class="side-pad">
            <p class="side-kicker">Explore the place</p>
            <h2>$map_title</h2>
            <p class="map-meta">$region</p>
          </div>
          <div id="miniMap" data-lat="$lat" data-lng="$lng" data-colour="$catcolour" data-initial="$initial" aria-label="Map showing the location associated with $name"></div>
          <div class="map-footer">
            <a href="$maplink">View full map &#8594;</a>
            <span>$coordinates</span>
          </div>
        </section>

        <section class="side-card side-pad">
          <p class="side-kicker">At a glance</p>
          <h2>About this legend</h2>
          <div class="facts">$facts</div>
        </section>

        $featured_sources
      </aside>
    </div>
  </div>

  $featured_related
</main>
<footer>Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; <a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener">Ko-fi</a> &#183; <a href="$base/privacy">Privacy</a></footer>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH" crossorigin="anonymous"></script>
<script src="$base/legend-page.js"></script>
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
    path = "index.html"
    text = io.open(path, encoding="utf-8").read()
    patterns = (
        (r'(<span id="heroCount">)\d+(</span>)', rf'\g<1>{total}\g<2>'),
        (r'(<span class="stat-num" id="statCount">)\d+(</span>)', rf'\g<1>{total}\g<2>'),
    )
    for pattern, replacement in patterns:
        text, changed = re.subn(pattern, replacement, text, count=1)
        if changed != 1:
            raise RuntimeError(f"Could not update homepage count using {pattern}")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def render_featured_legend(leg, featured, paras, srcs, rel, cats, meta,
                           slugmap, catname, maplink, page_path_url, desc,
                           jsonld, breadcrumb, breadcrumb_jsonld):
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
        section_heading = featured.get("section_heading") or "The story"
        featured_parts.append(f"<h2>{esc(section_heading)}</h2>")
        featured_parts.extend(f"<p>{esc(inline_text(p))}</p>" for p in paras[1:])
    featured_body = "".join(featured_parts) or '<p class="opening"></p>'

    fact_items = featured.get("facts") or {
        "Category": catname,
        "Region": leg.get("region", ""),
    }
    facts_html = "".join(
        f'<div class="fact"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'
        for label, value in fact_items.items()
    )

    if srcs:
        source_items = "".join(
            f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">'
            f'{esc(s["publisher"])} &#8594;</a>'
            + (f' <span class="source-tier">{esc(s["label"])}</span>' if s["label"] else "")
            + "</li>"
            for s in srcs
        )
        featured_sources = (
            '<section class="side-card side-pad"><p class="side-kicker">Sources</p>'
            '<h2>Further reading</h2>'
            '<p class="source-copy">Sources used to research and locate this legend.</p>'
            f'<ul class="source-list">{source_items}</ul></section>'
        )
    else:
        featured_sources = ""

    featured_cards = []
    for related in rel[:3]:
        related_cat = cats.get(related.get("category", ""), related.get("category", ""))
        related_colour = meta.get(related.get("category", ""), {}).get("colour", "#8b3a1a")
        featured_cards.append(
            f'<a class="related-card" style="--card-glow:{esc(related_colour)}" '
            f'href="{BASE}/{OUT_DIR}/{slugmap[related["name"]]}">'
            f'<span class="related-type">{esc(related_cat)}</span>'
            f'<span class="related-name">{esc(related["name"])}</span>'
            f'<span class="related-place">{esc(related.get("region", ""))}</span></a>'
        )
    if featured_cards:
        featured_related = (
            '<section class="related"><div class="shell">'
            '<div class="section-head"><div><p>Continue exploring</p>'
            '<h2>Related legends</h2></div>'
            f'<a href="{BASE}/{OUT_DIR}/">Browse all legends</a></div>'
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
    if has_image:
        hero_url = f"{BASE}/{image_path.replace(os.sep, '/')}"
        hero_media = f'<img src="{hero_url}" alt="{esc(featured.get("alt", ""))}"/>'
        hero_caption = (
            f'<span class="hero-caption">{esc(featured.get("caption", ""))}</span>'
            if featured.get("caption") else ""
        )
        ogimage = hero_url
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
            if leg.get("category", "") in meta else f"{BASE}/og/preview.png"
        )

    return FEATURED_PAGE.substitute(
        title=esc(f"{name} — Folklore of Britain & Ireland"),
        ogtitle=esc(name),
        desc=esc(inline_text(desc)),
        url=page_path_url,
        base=BASE,
        jsonld=jsonld,
        breadcrumb_jsonld=breadcrumb_jsonld,
        topnav=topnav_html("browse"),
        breadcrumb=breadcrumb,
        hero_media=hero_media,
        hero_caption=hero_caption,
        catcolour=esc(catcolour),
        catname=esc(catname),
        region=esc(leg.get("region", "")),
        name=esc(name),
        standfirst=esc(inline_text(leg.get("summary", ""))),
        featured_body=featured_body,
        maplink=esc(maplink),
        map_title=esc(featured.get("map_title") or leg.get("region", "")),
        lat=f"{lat:.6f}",
        lng=f"{lng:.6f}",
        initial=esc(name[:1]),
        coordinates=coordinates,
        facts=facts_html,
        featured_sources=featured_sources,
        featured_related=featured_related,
        ogimage=ogimage,
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

    written = 0
    for leg in legends:
        name = leg["name"]
        slug = slugmap[name]
        desc = short_desc(leg.get("summary", ""))
        # Full-page body: use the longer `detail` if present, else the summary.
        # Split on blank lines into paragraphs; first paragraph gets the drop cap.
        body_text = leg.get("detail") or leg.get("summary", "")
        paras = [p.strip() for p in body_text.split("\n\n") if p.strip()]
        body_html = "".join(
            f'<p class="{"summary" if i == 0 else "summary-cont"}">{esc(p)}</p>'
            for i, p in enumerate(paras)
        ) or '<p class="summary"></p>'
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
                         "name": "Folklore Map of Britain & Ireland", "url": BASE + "/"},
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
        jsonld = json.dumps(ld, ensure_ascii=False)
        # date_added/date_modified stay in the JSON-LD and sitemap, but are not
        # shown on the page (looked out of place).

        # Sourcing block: single line for one source, a labelled list for more.
        def src_link(s):
            tier = f' &#183; <span class="src-tier">{esc(s["label"])}</span>' if s["label"] else ""
            return (f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">'
                    f'{esc(s["publisher"])}</a>{tier}')
        if not srcs:
            sources_html = ""
        elif len(srcs) == 1:
            sources_html = f'<span class="src">Researched from {src_link(srcs[0])}</span>'
        else:
            lis = "".join(f"<li>{src_link(s)}</li>" for s in srcs)
            sources_html = (f'<div class="sources"><span class="sources-head">Researched from:'
                            f'</span><ul>{lis}</ul></div>')

        # Related legends carousel
        rel = related_map.get(name, [])
        if rel:
            cards = []
            for r in rel:
                rcat = cats.get(r.get("category", ""), r.get("category", ""))
                rcolour = meta.get(r.get("category", ""), {}).get("colour", "#8b3a1a")
                cards.append(
                    f'<a class="rel-card" href="{BASE}/{OUT_DIR}/{slugmap[r["name"]]}">'
                    f'<span class="rel-cat" style="background:{esc(rcolour)}">{esc(rcat)}</span>'
                    f'<span class="rel-name">{esc(r["name"])}</span>'
                    f'<span class="rel-region">{esc(r.get("region", ""))}</span></a>'
                )
            related_html = (
                '<section class="related"><div class="related-head">Related Legends</div>'
                '<div class="carousel">'
                '<button class="carousel-btn prev" type="button" aria-label="Scroll left">&#8249;</button>'
                '<div class="carousel-track">' + "".join(cards) + '</div>'
                '<button class="carousel-btn next" type="button" aria-label="Scroll right">&#8250;</button>'
                '</div></section>'
            )
        else:
            related_html = ""

        page_path_url = f"{BASE}/{OUT_DIR}/{slug}"

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
            {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumb_items},
            ensure_ascii=False) + '</script>'

        out = LEGACY_PAGE.format(
            title=esc(f"{name} — Folklore of Britain & Ireland"),
            ogtitle=esc(name),
            desc=esc(desc),
            url=page_path_url,
            base=BASE,
            jsonld=jsonld,
            catname=esc(catname),
            name=esc(name),
            region=esc(leg.get("region", "")),
            body=body_html,
            related=related_html,
            breadcrumb=breadcrumb,
            breadcrumb_jsonld=breadcrumb_jsonld,
            maplink=esc(maplink),
            sources=sources_html,
            watermark=meta.get(leg.get("category", ""), {}).get("iconPath", ""),
            catcolour=esc(meta.get(leg.get("category", ""), {}).get("colour", "#8b3a1a")),
            ogimage=f"{BASE}/og/category-{leg.get('category', '')}.png" if leg.get("category", "") in meta else f"{BASE}/og/preview.png",
            topnav_css=TOPNAV_CSS,
            topnav=topnav_html("browse"),
        )
        out = render_featured_legend(
            leg=leg,
            featured=featured_pages.get(name, {}),
            paras=paras,
            srcs=srcs,
            rel=rel,
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
        page = build_browse_page(
            page_title=f"{label} of Britain & Ireland — Folklore Map",
            desc=f"Browse {len(entries)} {label.lower()} from across British and Irish folklore — each pinned to the place its story is rooted.",
            url=url,
            h1=label,
            intro=cat_intros.get(c) or f"{len(entries)} {label.lower()} and related folklore from across Britain and Ireland.",
            crumb=label,
            nav_html=nav_links(cat_nav_items, c),
            cards_html=cards,
            ogimage=f"{BASE}/og/category-{c}.png" if c in meta else None,
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
        page = build_browse_page(
            page_title=f"Folklore of {rn} — Myths, Legends & Ghosts",
            desc=f"{len(entries)} myths, legends, ghosts and folklore entries rooted in {rn}.",
            url=url,
            h1=f"Folklore of {rn}",
            intro=region_intros.get(t) or f"{len(entries)} legends, ghosts and folklore entries rooted in {rn}.",
            crumb=rn,
            nav_html=nav_links(nation_nav_items, t),
            cards_html=cards,
        )
        with io.open(os.path.join(reg_dir, f"{t}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        browse_urls.append(url)

    # ── Themed collection pages (curated, cross-cutting) ───────────────────
    col_dir = os.path.join(OUT_DIR, "collection")
    collections = load_collections()
    built_collections = []  # (slug, title, count) for nav / index / sitemap
    if collections:
        os.makedirs(col_dir, exist_ok=True)
        # Resolve membership first so we can build a shared nav of siblings.
        resolved = []
        for col in collections:
            members = sorted(
                (l for l in legends if matches_collection(l, col.get("match", {}))),
                key=lambda l: l["name"].lower(),
            )
            if len(members) >= MIN_COLLECTION:
                resolved.append((col, members))
        col_nav_items = [
            (f"{BASE}/{OUT_DIR}/collection/{col['slug']}", col["title"], col["slug"])
            for col, _ in resolved
        ]
        for col, members in resolved:
            slug = col["slug"]
            total = len(members)
            desc = short_desc(col["intro"], 155)
            total_pages = max(1, (total + COLLECTION_PER_PAGE - 1) // COLLECTION_PER_PAGE)
            for page_no in range(1, total_pages + 1):
                start = (page_no - 1) * COLLECTION_PER_PAGE
                page_members = members[start:start + COLLECTION_PER_PAGE]
                url = collection_page_url(slug, page_no)
                cards = "\n".join(
                    browse_card(l, slugmap, cats, meta, show_cat=True, show_summary=True)
                    for l in page_members
                )
                # Page 2+ get a "(page N of M)" suffix in title/intro for clarity.
                page_tag = "" if total_pages == 1 else f" (page {page_no} of {total_pages})"
                collection_jsonld = json.dumps({
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": col["title"] + page_tag,
                    "description": desc,
                    "url": url,
                    "isPartOf": {"@type": "WebSite",
                                 "name": "Folklore Map of Britain & Ireland", "url": BASE + "/"},
                    "mainEntity": {
                        "@type": "ItemList",
                        "numberOfItems": len(page_members),
                        "itemListElement": [
                            {"@type": "ListItem", "position": start + i + 1,
                             "url": f"{BASE}/{OUT_DIR}/{slugmap[m['name']]}", "name": m["name"]}
                            for i, m in enumerate(page_members)
                        ],
                    },
                }, ensure_ascii=False)
                # rel=prev/next help crawlers understand the paginated series.
                rel_links = ""
                if page_no > 1:
                    rel_links += f'<link rel="prev" href="{collection_page_url(slug, page_no - 1)}"/>\n'
                if page_no < total_pages:
                    rel_links += f'<link rel="next" href="{collection_page_url(slug, page_no + 1)}"/>\n'
                page = build_browse_page(
                    page_title=f"{col['title']}{page_tag} — Folklore Map of Britain & Ireland",
                    desc=desc,
                    url=url,
                    h1=col["title"],
                    intro=col["intro"],
                    crumb=col["title"] + page_tag,
                    nav_html=nav_links(col_nav_items, slug),
                    cards_html=cards,
                    jsonld=collection_jsonld,
                    head_extra=rel_links,
                    after_grid=pagination_html(slug, page_no, total_pages),
                    nav_active="collections",
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
                land_cards.append(
                    f'<a class="b-card" href="{curl}">'
                    f'<span class="b-name">{esc(col["title"])}</span>'
                    f'<span class="b-region">{len(members)} legends</span>'
                    f'<span class="b-summary">{esc(col["intro"])}</span></a>'
                )
            land_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": "Themed Collections",
                "description": "Themed collections of British and Irish folklore — black dogs, "
                               "standing stones, holy wells, Arthurian places and more.",
                "url": land_url,
                "isPartOf": {"@type": "WebSite",
                             "name": "Folklore Map of Britain & Ireland", "url": BASE + "/"},
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
                page_title="Themed Collections — Folklore Map of Britain & Ireland",
                desc="Explore British and Irish folklore by theme — black dogs, standing stones, "
                     "holy wells, Arthurian places, legends of the sea and more.",
                url=land_url,
                h1="Themed Collections",
                intro="Curated gatherings of legends that share a creature, a landscape or a tradition — "
                      "ways into the map that the category and region lists don't capture.",
                crumb="Collections",
                nav_html="",
                cards_html="\n".join(land_cards),
                jsonld=land_jsonld,
                nav_active="collections",
            )
            with io.open(os.path.join(OUT_DIR, "collections.html"), "w", encoding="utf-8") as f:
                f.write(land_page)
            browse_urls.append(land_url)

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
        ('<div class="browse-sec"><h2>Themed collections</h2><div class="region-links">'
         + collection_links + '</div></div>') if built_collections else ''
    )
    browse_sections = (
        collection_sec
        + '<div class="browse-sec"><h2>Browse by category</h2><div class="cat-links">' + cat_links + '</div></div>'
        '<div class="browse-sec"><h2>Browse by region</h2><div class="region-links">' + region_links + '</div></div>'
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
<title>All Legends &#8212; Folklore Map of Britain &amp; Ireland</title>
<meta name="description" content="Browse all {written} myths, legends, ghosts and folklore entries across Britain and Ireland."/>
<link rel="canonical" href="{BASE}/{OUT_DIR}/"/>
<link rel="icon" type="image/png" href="{BASE}/favicon.png"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Marcellus&family=Spectral:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e0d0b0;color:#2c1f0e;font-family:'Spectral',serif;min-height:100vh}}
.site-banner{{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#3d2510 0%,#1a0e06 45%,#2c1f0e 100%);padding:16px 20px;text-align:center}}
.site-banner::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}}
.site-banner::after{{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}}
.banner-link{{display:inline-flex;align-items:center;gap:13px;text-decoration:none}}
.banner-emblem{{width:48px;height:48px;object-fit:contain;flex-shrink:0}}
.banner-text{{display:flex;flex-direction:column;align-items:center;line-height:1.15}}
.banner-title{{font-family:'Marcellus',serif;font-size:21px;font-weight:400;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}}
.banner-title i{{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}}
.banner-sub{{font-family:'Spectral',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}}
@media(max-width:560px){{.banner-title{{font-size:15px}}.banner-emblem{{width:38px;height:38px}}.banner-sub{{font-size:11px}}}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 20px 60px}}
h1{{font-family:'Marcellus',serif;font-size:26px;margin-bottom:18px}}
.az{{column-count:8;column-gap:20px}}
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
.browse-sec{{margin-bottom:26px}}
.browse-sec h2,.azh{{font-family:'Marcellus',serif;font-size:18px;margin-bottom:13px;color:#2c1f0e}}
.azh{{margin-top:6px}}
.cat-links,.region-links{{display:flex;flex-wrap:wrap;gap:9px}}
.cat-links a,.region-links a{{display:inline-flex;align-items:center;gap:7px;font-family:'Marcellus',serif;font-size:13px;color:#2c1f0e;background:#f2e8d5;border:1px solid #b09060;border-radius:4px;padding:7px 13px;text-decoration:none}}
.cat-links a:hover,.region-links a:hover{{border-color:#c4622a}}
.c-count{{font-size:11px;color:#5c4a2a;font-style:italic}}
.c-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;flex-shrink:0}}
{TOPNAV_CSS}
</style></head>
<body>
{topnav_html("browse")}
<header class="site-banner"><a class="banner-link" href="{BASE}/"><img src="{BASE}/green-man.png" class="banner-emblem" alt=""/><span class="banner-text"><span class="banner-title"><i>&#10022;</i> Folklore Map of Britain &amp; Ireland <i>&#10022;</i></span><span class="banner-sub">Myths, Legends &amp; Spectral Encounters</span></span></a></header>
<div class="wrap"><h1>All Legends ({written})</h1>{browse_sections}<div class="az">
{az_content}
</div></div>
<footer style="text-align:center;padding:24px 20px;font-size:12px;color:#5c4a2a">Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; <a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener" style="color:#5c4a2a">&#9749; Ko-fi</a> &#183; <a href="{BASE}/privacy" style="color:#5c4a2a">Privacy</a></footer>
</body></html>"""
    with io.open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # sitemap.xml — legend pages carry their own date_modified as lastmod, so the
    # signal is honest; app/aggregation pages use the build date.
    urls = [f"{BASE}/", f"{BASE}/{OUT_DIR}/", f"{BASE}/about", f"{BASE}/updates", f"{BASE}/privacy", f"{BASE}/feed.xml"]
    urls += browse_urls
    urls += [f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}" for l in legends]
    lastmod_map = {f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}": (l.get("date_modified") or today)
                   for l in legends}
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for i, u in enumerate(urls):
        pr = "1.0" if i == 0 else ("0.8" if i == 1 else "0.6")
        lm = lastmod_map.get(u, today)
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
        '  <title>Folklore Map of Britain &amp; Ireland — New Legends</title>\n'
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

    print(f"Generated {written} legend pages + index + sitemap ({len(urls)} URLs) + feed.xml ({len(recent)} items)")


if __name__ == "__main__":
    build()
