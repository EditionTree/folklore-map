# -*- coding: utf-8 -*-
"""
generate_pages.py — emit static, SEO-indexable HTML pages, one per legend,
plus an A-Z index page and a full sitemap.xml.

These pages are served by Cloudflare Pages independently of the main map app.
A visitor only ever loads one of them at a time (arriving from search or a
shared link); the interactive map (map.html) is unaffected.

Run after legends.json changes:  python generate_pages.py
"""
import json, io, os, re, unicodedata, html, urllib.parse, datetime, math

BASE = "https://folklorefinder.uk"
OUT_DIR = "legends"

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


def footer_html():
    return ('<footer style="text-align:center;padding:30px 20px;font-size:12px;color:#5c4a2a">'
            'Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; '
            '<a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener" style="color:#5c4a2a">&#9749; Ko-fi</a> &#183; '
            '<a href="' + BASE + '/privacy.html" style="color:#5c4a2a">Privacy</a></footer>')


def nav_links(items, active):
    """items: list of (url, label, key)."""
    parts = ['<nav class="browse-nav">']
    for url, label, key in items:
        cls = ' class="active"' if key == active else ''
        parts.append('<a href="' + url + '"' + cls + '>' + esc(label) + '</a>')
    parts.append('</nav>')
    return ''.join(parts)


def browse_card(leg, slugmap, cats, meta, show_cat):
    cat = leg.get("category", "")
    href = BASE + "/" + OUT_DIR + "/" + slugmap[leg["name"]] + ".html"
    chip = ""
    if show_cat:
        colour = meta.get(cat, {}).get("colour", "#8b3a1a")
        chip = ('<span class="b-cat" style="background:' + esc(colour) + '">'
                + esc(cats.get(cat, cat)) + '</span>')
    return ('<a class="b-card" href="' + href + '">' + chip
            + '<span class="b-name">' + esc(leg["name"]) + '</span>'
            + '<span class="b-region">' + esc(leg.get("region", "")) + '</span></a>')


BROWSE_STYLE = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#e0d0b0;color:#2c1f0e;font-family:'Crimson Text',serif;line-height:1.7;min-height:100vh}
.site-banner{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#3d2510 0%,#1a0e06 45%,#2c1f0e 100%);padding:16px 20px;text-align:center}
.site-banner::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}
.site-banner::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}
.banner-link{display:inline-flex;align-items:center;gap:13px;text-decoration:none}
.banner-emblem{width:48px;height:48px;object-fit:contain;flex-shrink:0}
.banner-text{display:flex;flex-direction:column;align-items:center;line-height:1.15}
.banner-title{font-family:'Cinzel',serif;font-size:21px;font-weight:600;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}
.banner-title i{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}
.banner-sub{font-family:'Crimson Text',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}
@media(max-width:560px){.banner-title{font-size:15px}.banner-emblem{width:38px;height:38px}.banner-sub{font-size:11px}}
.wrap{max-width:760px;margin:0 auto;padding:24px 20px 60px}
.crumb{font-size:12px;color:#5c4a2a;margin-bottom:14px}
.crumb a{color:#8b3a1a;text-decoration:none}
.browse-h1{font-family:'Cinzel',serif;font-size:27px;margin-bottom:6px;color:#2c1f0e;line-height:1.15}
.browse-intro{font-size:16px;color:#5c4a2a;margin-bottom:16px}
.browse-nav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.browse-nav a{font-family:'Cinzel',serif;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#8b3a1a;border:1px solid #b09060;border-radius:3px;padding:5px 11px;text-decoration:none}
.browse-nav a:hover,.browse-nav a.active{background:#8b3a1a;color:#f2e8d5;border-color:#8b3a1a}
.browse-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.b-card{background:#f2e8d5;border:1px solid #b09060;border-radius:5px;padding:14px 15px;text-decoration:none;color:#2c1f0e;transition:border-color .15s,transform .1s}
.b-card:hover{border-color:#c4622a;transform:translateY(-2px)}
.b-card span{display:block}
.b-cat{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#8b3a1a;padding:2px 8px;border-radius:3px;margin-bottom:8px;width:max-content;max-width:100%}
.b-name{font-family:'Cinzel',serif;font-size:15px;line-height:1.25;margin-bottom:4px}
.b-region{font-style:italic;font-size:12px;color:#5c4a2a}
.back{display:inline-block;margin-top:24px;font-size:13px;color:#5c4a2a}
@media(max-width:560px){.browse-grid{grid-template-columns:1fr 1fr}}
@media(max-width:380px){.browse-grid{grid-template-columns:1fr}}
"""


def build_browse_page(page_title, desc, url, h1, intro, crumb, nav_html, cards_html):
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
            '<meta property="og:image" content="' + BASE + '/og/preview.png"/>\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">\n'
            '<style>' + BROWSE_STYLE + '</style></head>\n<body>\n'
            + banner_html() + '\n<div class="wrap">\n'
            '<nav class="crumb"><a href="' + BASE + '/">Home</a> &#8250; '
            '<a href="' + BASE + '/' + OUT_DIR + '/">All legends</a> &#8250; '
            '<span>' + esc(crumb) + '</span></nav>\n'
            '<h1 class="browse-h1">' + esc(h1) + '</h1>\n'
            '<p class="browse-intro">' + esc(intro) + '</p>\n'
            + nav_html + '\n<div class="browse-grid">\n' + cards_html
            + '\n</div>\n<a class="back" href="' + BASE + '/' + OUT_DIR + '/">&#8592; Browse all legends</a>\n'
            '</div>\n' + footer_html() + '\n</body></html>')


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "legend"


def esc(s):
    return html.escape(s or "", quote=True)


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


PAGE = """<!DOCTYPE html>
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
<meta property="og:image" content="{base}/og/preview.png"/>
<meta property="og:site_name" content="Folklore Map of Britain &amp; Ireland"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{ogtitle}"/>
<meta name="twitter:description" content="{desc}"/>
<meta name="twitter:image" content="{base}/og/preview.png"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<script type="application/ld+json">{jsonld}</script>
{breadcrumb_jsonld}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e0d0b0;color:#2c1f0e;font-family:'Crimson Text',serif;line-height:1.7;min-height:100vh}}
.site-banner{{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#3d2510 0%,#1a0e06 45%,#2c1f0e 100%);padding:16px 20px;text-align:center}}
.site-banner::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}}
.site-banner::after{{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}}
.banner-link{{display:inline-flex;align-items:center;gap:13px;text-decoration:none}}
.banner-emblem{{width:48px;height:48px;object-fit:contain;flex-shrink:0}}
.banner-text{{display:flex;flex-direction:column;align-items:center;line-height:1.15}}
.banner-title{{font-family:'Cinzel',serif;font-size:21px;font-weight:600;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}}
.banner-title i{{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}}
.banner-sub{{font-family:'Crimson Text',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}}
.watermark{{position:absolute;top:26px;right:24px;width:88px;height:88px;color:#8b3a1a;opacity:.1;pointer-events:none;z-index:0}}
@media(max-width:560px){{.banner-title{{font-size:15px}}.banner-emblem{{width:38px;height:38px}}.banner-sub{{font-size:11px}}}}
.wrap{{max-width:680px;margin:0 auto;padding:0 20px 60px}}
.card{{position:relative;overflow:hidden;background:#f2e8d5;border:1px solid #b09060;border-radius:6px;margin-top:30px;padding:32px;box-shadow:0 4px 20px rgba(44,31,14,.18)}}
.card>*:not(.watermark){{position:relative;z-index:1}}
.card>.watermark{{position:absolute;top:26px;right:24px;width:88px;height:88px;z-index:0}}
.cat{{font-family:'Cinzel',serif;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#fff;background:#8b3a1a;display:inline-block;padding:3px 10px;border-radius:2px}}
h1{{font-family:'Cinzel',serif;font-size:30px;margin:14px 0 4px;color:#2c1f0e;line-height:1.15}}
.region{{font-style:italic;color:#5c4a2a;margin-bottom:18px}}
.crumb{{font-size:12.5px;color:#5c4a2a;margin-bottom:16px;line-height:1.5}}
.crumb a{{color:#8b3a1a;text-decoration:none}}
.crumb a:hover{{text-decoration:underline}}
.crumb .sep{{color:#b09060;margin:0 6px}}
.crumb .here{{color:#5c4a2a}}
.summary{{font-size:17px}}
.summary::first-letter{{font-family:'Cinzel',serif;font-size:2.4em;font-weight:600;color:#8b3a1a;line-height:1}}
.summary-cont{{font-size:17px;margin-top:14px}}
.cta{{display:inline-block;margin-top:26px;background:#2c1f0e;color:#f2e8d5;font-family:'Cinzel',serif;font-size:13px;letter-spacing:.08em;text-transform:uppercase;padding:12px 22px;border-radius:3px;text-decoration:none}}
.cta:hover{{background:#8b3a1a}}
.src{{display:block;margin-top:18px;font-size:13px;font-style:italic;color:#5c4a2a}}
.src a{{color:#8b3a1a}}
.back{{display:inline-block;margin-top:22px;font-size:13px;color:#5c4a2a}}
.related{{margin-top:36px}}
.related-head{{font-family:'Cinzel',serif;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#8b3a1a;display:flex;align-items:center;gap:12px;margin-bottom:16px}}
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
.rel-name{{font-family:'Cinzel',serif;font-size:15px;line-height:1.25;margin-bottom:4px}}
.rel-region{{font-style:italic;font-size:12px;color:#5c4a2a}}
.carousel-btn{{position:absolute;top:42%;transform:translateY(-50%);width:34px;height:34px;border-radius:50%;border:1px solid #b09060;background:#f2e8d5;color:#8b3a1a;font-family:'Cinzel',serif;font-size:18px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;box-shadow:0 2px 8px rgba(44,31,14,.25)}}
.carousel-btn:hover{{background:#8b3a1a;color:#f2e8d5}}
.carousel-btn.prev{{left:-10px}}
.carousel-btn.next{{right:-10px}}
@media(max-width:560px){{.carousel-btn{{display:none}}.rel-card{{flex-basis:170px}}}}
footer{{text-align:center;padding:30px 20px;font-size:12px;color:#5c4a2a}}
</style>
</head>
<body>
<header class="site-banner"><a class="banner-link" href="{base}/"><img src="{base}/green-man.png" class="banner-emblem" alt=""/><span class="banner-text"><span class="banner-title"><i>&#10022;</i> Folklore Map of Britain &amp; Ireland <i>&#10022;</i></span><span class="banner-sub">Myths, Legends &amp; Spectral Encounters</span></span></a></header>
<div class="wrap">
{breadcrumb}
<article class="card">
<span class="cat" style="background:{catcolour}">{catname}</span>
<h1>{name}</h1>
<div class="region">{region}</div>
{body}
<a class="cta" href="{maplink}">Explore on the interactive map &#8594;</a>
<span class="src">Source: <a href="{src}" target="_blank" rel="noopener">{srchost}</a></span>
<svg class="watermark" viewBox="0 0 512 512" aria-hidden="true"><path d="{watermark}" fill="currentColor"/></svg>
</article>
{related}
<a class="back" href="{base}/legends/">&#8592; Browse all legends</a>
</div>
<footer>Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; <a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener" style="color:#5c4a2a">&#9749; Ko-fi</a> &#183; <a href="{base}/privacy.html" style="color:#5c4a2a">Privacy</a></footer>
<script>
document.querySelectorAll('.carousel').forEach(function(c){{
  var t=c.querySelector('.carousel-track');
  var p=c.querySelector('.prev'), n=c.querySelector('.next');
  if(p)p.addEventListener('click',function(){{t.scrollBy({{left:-220,behavior:'smooth'}});}});
  if(n)n.addEventListener('click',function(){{t.scrollBy({{left:220,behavior:'smooth'}});}});
}});
</script>
</body>
</html>
"""


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


def build():
    d = json.load(io.open("legends.json", encoding="utf-8"))
    cats = d.get("categories", {})
    legends = sorted(d["legends"], key=lambda l: l["name"].lower())
    meta = load_category_meta()
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
            parts.append((cats.get(cat, cat), f"{BASE}/{OUT_DIR}/category/{cat}.html"))
        rtags = (set(leg.get("tags") or []) - THEMATIC_TAGS) & generated_regions
        counties = sorted(t for t in rtags if t not in NATIONS)
        nats = sorted(t for t in rtags if t in NATIONS)
        rtag = counties[0] if counties else (nats[0] if nats else None)
        if rtag:
            parts.append((prettify_region(rtag), f"{BASE}/{OUT_DIR}/region/{rtag}.html"))
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
        maplink = f"{BASE}/map.html?legend=" + urllib.parse.quote(name)
        src = leg.get("source", "")
        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "CreativeWork",
            "name": name,
            "description": desc,
            "url": f"{BASE}/{OUT_DIR}/{slug}.html",
            "genre": "Folklore",
            "about": {
                "@type": "Place",
                "name": leg.get("region", ""),
                "geo": {"@type": "GeoCoordinates",
                        "latitude": leg.get("lat"), "longitude": leg.get("lng")},
            },
            "isPartOf": {"@type": "WebSite",
                         "name": "Folklore Map of Britain & Ireland", "url": BASE + "/"},
        }, ensure_ascii=False)

        # Related legends carousel
        rel = related_map.get(name, [])
        if rel:
            cards = []
            for r in rel:
                rcat = cats.get(r.get("category", ""), r.get("category", ""))
                rcolour = meta.get(r.get("category", ""), {}).get("colour", "#8b3a1a")
                cards.append(
                    f'<a class="rel-card" href="{BASE}/{OUT_DIR}/{slugmap[r["name"]]}.html">'
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

        page_path_url = f"{BASE}/{OUT_DIR}/{slug}.html"

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

        out = PAGE.format(
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
            src=esc(src),
            srchost=esc(host_of(src)),
            watermark=meta.get(leg.get("category", ""), {}).get("iconPath", ""),
            catcolour=esc(meta.get(leg.get("category", ""), {}).get("colour", "#8b3a1a")),
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
    cat_nav_items = [(f"{BASE}/{OUT_DIR}/category/{c}.html", cats.get(c, c), c) for c in cat_order]
    for c in cat_order:
        entries = sorted(cat_groups[c], key=lambda l: l["name"].lower())
        label = cats.get(c, c)
        url = f"{BASE}/{OUT_DIR}/category/{c}.html"
        cards = "\n".join(browse_card(l, slugmap, cats, meta, show_cat=False) for l in entries)
        page = build_browse_page(
            page_title=f"{label} of Britain &amp; Ireland — Folklore Map",
            desc=f"Browse {len(entries)} {label.lower()} from across British and Irish folklore — each pinned to the place its story is rooted.",
            url=url,
            h1=label,
            intro=f"{len(entries)} {label.lower()} and related folklore from across Britain and Ireland.",
            crumb=label,
            nav_html=nav_links(cat_nav_items, c),
            cards_html=cards,
        )
        with io.open(os.path.join(cat_dir, f"{c}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        browse_urls.append(url)

    # Region pages — nations always, other areas only if >= 4 entries (avoid thin pages)
    region_eligible = [t for t in region_groups if t in NATIONS or len(region_groups[t]) >= 4]
    region_order = sorted(region_eligible, key=lambda t: (0 if t in NATIONS else 1, -len(region_groups[t])))
    nation_nav_items = [(f"{BASE}/{OUT_DIR}/region/{t}.html", prettify_region(t), t)
                        for t in NATIONS if t in region_groups]
    for t in region_order:
        entries = sorted(region_groups[t], key=lambda l: l["name"].lower())
        rn = prettify_region(t)
        url = f"{BASE}/{OUT_DIR}/region/{t}.html"
        cards = "\n".join(browse_card(l, slugmap, cats, meta, show_cat=True) for l in entries)
        page = build_browse_page(
            page_title=f"Folklore of {rn} — Myths, Legends & Ghosts",
            desc=f"{len(entries)} myths, legends, ghosts and folklore entries rooted in {rn}.",
            url=url,
            h1=f"Folklore of {rn}",
            intro=f"{len(entries)} legends, ghosts and folklore entries rooted in {rn}.",
            crumb=rn,
            nav_html=nav_links(nation_nav_items, t),
            cards_html=cards,
        )
        with io.open(os.path.join(reg_dir, f"{t}.html"), "w", encoding="utf-8") as f:
            f.write(page)
        browse_urls.append(url)

    # Browse sections for the A-Z index page
    cat_links = "".join(
        '<a href="' + f"{BASE}/{OUT_DIR}/category/{c}.html" + '">'
        '<span class="c-dot" style="background:' + esc(meta.get(c, {}).get("colour", "#8b3a1a")) + '"></span>'
        + esc(cats.get(c, c)) + ' <span class="c-count">' + str(len(cat_groups[c])) + '</span></a>'
        for c in cat_order
    )
    region_links = "".join(
        '<a href="' + f"{BASE}/{OUT_DIR}/region/{t}.html" + '">'
        + esc(prettify_region(t)) + ' <span class="c-count">' + str(len(region_groups[t])) + '</span></a>'
        for t in region_order
    )
    browse_sections = (
        '<div class="browse-sec"><h2>Browse by category</h2><div class="cat-links">' + cat_links + '</div></div>'
        '<div class="browse-sec"><h2>Browse by region</h2><div class="region-links">' + region_links + '</div></div>'
        '<h2 class="azh">A&#8211;Z</h2>'
    )

    # A-Z index page
    items = "\n".join(
        f'<li><a href="{BASE}/{OUT_DIR}/{slugmap[l["name"]]}.html">{esc(l["name"])}</a>'
        f' <span>{esc(l.get("region",""))}</span></li>'
        for l in legends
    )
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
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&family=Crimson+Text:ital,wght@0,400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e0d0b0;color:#2c1f0e;font-family:'Crimson Text',serif;min-height:100vh}}
.site-banner{{position:relative;background:linear-gradient(135deg,rgba(196,98,42,0.18) 0%,rgba(176,144,96,0.06) 35%,transparent 60%),linear-gradient(180deg,#3d2510 0%,#1a0e06 45%,#2c1f0e 100%);padding:16px 20px;text-align:center}}
.site-banner::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#8b3a1a 15%,#b09060 50%,#8b3a1a 85%,transparent)}}
.site-banner::after{{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(176,144,96,.6) 20%,rgba(196,98,42,.8) 50%,rgba(176,144,96,.6) 80%,transparent)}}
.banner-link{{display:inline-flex;align-items:center;gap:13px;text-decoration:none}}
.banner-emblem{{width:48px;height:48px;object-fit:contain;flex-shrink:0}}
.banner-text{{display:flex;flex-direction:column;align-items:center;line-height:1.15}}
.banner-title{{font-family:'Cinzel',serif;font-size:21px;font-weight:600;color:#f2e8d5;letter-spacing:.09em;display:flex;align-items:center;justify-content:center;gap:9px}}
.banner-title i{{color:#c4622a;font-style:normal;font-size:.6em;flex-shrink:0}}
.banner-sub{{font-family:'Crimson Text',serif;font-size:12px;font-style:italic;color:rgba(176,144,96,.8);letter-spacing:.04em}}
@media(max-width:560px){{.banner-title{{font-size:15px}}.banner-emblem{{width:38px;height:38px}}.banner-sub{{font-size:11px}}}}
.wrap{{max-width:760px;margin:0 auto;padding:24px 20px 60px}}
h1{{font-family:'Cinzel',serif;font-size:26px;margin-bottom:18px}}
ul{{list-style:none;columns:2;column-gap:30px}}
@media(max-width:560px){{ul{{columns:1}}}}
li{{break-inside:avoid;padding:5px 0;border-bottom:.5px solid rgba(176,144,96,.3)}}
li a{{color:#8b3a1a;text-decoration:none;font-size:16px}}
li span{{display:block;font-size:12px;font-style:italic;color:#5c4a2a}}
.browse-sec{{margin-bottom:26px}}
.browse-sec h2,.azh{{font-family:'Cinzel',serif;font-size:18px;margin-bottom:13px;color:#2c1f0e}}
.azh{{margin-top:6px}}
.cat-links,.region-links{{display:flex;flex-wrap:wrap;gap:9px}}
.cat-links a,.region-links a{{display:inline-flex;align-items:center;gap:7px;font-family:'Cinzel',serif;font-size:13px;color:#2c1f0e;background:#f2e8d5;border:1px solid #b09060;border-radius:4px;padding:7px 13px;text-decoration:none}}
.cat-links a:hover,.region-links a:hover{{border-color:#c4622a}}
.c-count{{font-size:11px;color:#5c4a2a;font-style:italic}}
.c-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;flex-shrink:0}}
</style></head>
<body>
<header class="site-banner"><a class="banner-link" href="{BASE}/"><img src="{BASE}/green-man.png" class="banner-emblem" alt=""/><span class="banner-text"><span class="banner-title"><i>&#10022;</i> Folklore Map of Britain &amp; Ireland <i>&#10022;</i></span><span class="banner-sub">Myths, Legends &amp; Spectral Encounters</span></span></a></header>
<div class="wrap"><h1>All Legends ({written})</h1>{browse_sections}<ul>
{items}
</ul></div>
<footer style="text-align:center;padding:24px 20px;font-size:12px;color:#5c4a2a">Part of the Folklore Map of Britain &amp; Ireland &#183; &#169; EditionTree &#183; <a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener" style="color:#5c4a2a">&#9749; Ko-fi</a> &#183; <a href="{BASE}/privacy.html" style="color:#5c4a2a">Privacy</a></footer>
</body></html>"""
    with io.open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # sitemap.xml
    today = datetime.date.today().isoformat()
    urls = [f"{BASE}/", f"{BASE}/{OUT_DIR}/", f"{BASE}/about.html", f"{BASE}/updates.html", f"{BASE}/privacy.html"]
    urls += browse_urls
    urls += [f"{BASE}/{OUT_DIR}/{slugmap[l['name']]}.html" for l in legends]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for i, u in enumerate(urls):
        pr = "1.0" if i == 0 else ("0.8" if i == 1 else "0.6")
        sm.append(f"  <url><loc>{u}</loc><lastmod>{today}</lastmod><priority>{pr}</priority></url>")
    sm.append("</urlset>")
    with io.open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")

    print(f"Generated {written} legend pages + index + sitemap ({len(urls)} URLs)")


if __name__ == "__main__":
    build()
