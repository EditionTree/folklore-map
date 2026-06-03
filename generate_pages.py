# -*- coding: utf-8 -*-
"""
generate_pages.py — emit static, SEO-indexable HTML pages, one per legend,
plus an A-Z index page and a full sitemap.xml.

These pages are served by GitHub Pages independently of the main map app.
A visitor only ever loads one of them at a time (arriving from search or a
shared link); the interactive map (index.html) is unaffected.

Run after legends.json changes:  python generate_pages.py
"""
import json, io, os, re, unicodedata, html, urllib.parse, datetime

BASE = "https://editiontree.github.io/folklore-map"
OUT_DIR = "legends"


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
<meta property="og:site_name" content="Folklore Map of the British Isles"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{ogtitle}"/>
<meta name="twitter:description" content="{desc}"/>
<meta name="twitter:image" content="{base}/og/preview.png"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<script type="application/ld+json">{jsonld}</script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e0d0b0;color:#2c1f0e;font-family:'Crimson Text',serif;line-height:1.7;min-height:100vh}}
header{{background:linear-gradient(180deg,#1e1408,#2c1f0e);padding:14px 20px;text-align:center;border-bottom:1px solid rgba(176,144,96,.4)}}
header a{{color:#f2e8d5;text-decoration:none;font-family:'Cinzel',serif;font-size:15px;letter-spacing:.08em}}
.wrap{{max-width:680px;margin:0 auto;padding:0 20px 60px}}
.card{{background:#f2e8d5;border:1px solid #b09060;border-radius:6px;margin-top:30px;padding:32px;box-shadow:0 4px 20px rgba(44,31,14,.18)}}
.cat{{font-family:'Cinzel',serif;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#fff;background:#8b3a1a;display:inline-block;padding:3px 10px;border-radius:2px}}
h1{{font-family:'Cinzel',serif;font-size:30px;margin:14px 0 4px;color:#2c1f0e;line-height:1.15}}
.region{{font-style:italic;color:#5c4a2a;margin-bottom:18px}}
.summary{{font-size:17px}}
.summary::first-letter{{font-family:'Cinzel',serif;font-size:2.4em;font-weight:600;color:#8b3a1a;line-height:1}}
.cta{{display:inline-block;margin-top:26px;background:#2c1f0e;color:#f2e8d5;font-family:'Cinzel',serif;font-size:13px;letter-spacing:.08em;text-transform:uppercase;padding:12px 22px;border-radius:3px;text-decoration:none}}
.cta:hover{{background:#8b3a1a}}
.src{{display:block;margin-top:18px;font-size:13px;font-style:italic;color:#5c4a2a}}
.src a{{color:#8b3a1a}}
.back{{display:inline-block;margin-top:22px;font-size:13px;color:#5c4a2a}}
footer{{text-align:center;padding:30px 20px;font-size:12px;color:#5c4a2a}}
</style>
</head>
<body>
<header><a href="{base}/"><img src="{base}/green-man.png" alt="" width="30" height="30" style="vertical-align:middle;margin-right:10px"/>Folklore Map of the British Isles</a></header>
<div class="wrap">
<article class="card">
<span class="cat">{catname}</span>
<h1>{name}</h1>
<div class="region">{region}</div>
<p class="summary">{summary}</p>
<a class="cta" href="{maplink}">Explore on the interactive map &#8594;</a>
<span class="src">Source: <a href="{src}" target="_blank" rel="noopener">{srchost}</a></span>
</article>
<a class="back" href="{base}/legends/">&#8592; Browse all legends</a>
</div>
<footer>Part of the Folklore Map of the British Isles &#183; &#169; EditionTree</footer>
</body>
</html>
"""


def build():
    d = json.load(io.open("legends.json", encoding="utf-8"))
    cats = d.get("categories", {})
    legends = sorted(d["legends"], key=lambda l: l["name"].lower())
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

    written = 0
    for leg in legends:
        name = leg["name"]
        slug = slugmap[name]
        desc = short_desc(leg.get("summary", ""))
        catname = cats.get(leg.get("category", ""), leg.get("category", "Legend"))
        maplink = f"{BASE}/?legend=" + urllib.parse.quote(name)
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
                         "name": "Folklore Map of the British Isles", "url": BASE + "/"},
        }, ensure_ascii=False)

        page_path_url = f"{BASE}/{OUT_DIR}/{slug}.html"
        out = PAGE.format(
            title=esc(f"{name} — Folklore of the British Isles"),
            ogtitle=esc(name),
            desc=esc(desc),
            url=page_path_url,
            base=BASE,
            jsonld=jsonld,
            catname=esc(catname),
            name=esc(name),
            region=esc(leg.get("region", "")),
            summary=esc(leg.get("summary", "")),
            maplink=esc(maplink),
            src=esc(src),
            srchost=esc(host_of(src)),
        )
        with io.open(os.path.join(OUT_DIR, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(out)
        written += 1

    # A-Z index page
    items = "\n".join(
        f'<li><a href="{BASE}/{OUT_DIR}/{slugmap[l["name"]]}.html">{esc(l["name"])}</a>'
        f' <span>{esc(l.get("region",""))}</span></li>'
        for l in legends
    )
    index_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>All Legends &#8212; Folklore Map of the British Isles</title>
<meta name="description" content="Browse all {written} myths, legends, ghosts and folklore entries across Britain and Ireland."/>
<link rel="canonical" href="{BASE}/{OUT_DIR}/"/>
<link rel="icon" type="image/png" href="{BASE}/favicon.png"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&family=Crimson+Text:ital,wght@0,400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e0d0b0;color:#2c1f0e;font-family:'Crimson Text',serif;min-height:100vh}}
header{{background:linear-gradient(180deg,#1e1408,#2c1f0e);padding:14px 20px;text-align:center;border-bottom:1px solid rgba(176,144,96,.4)}}
header a{{color:#f2e8d5;text-decoration:none;font-family:'Cinzel',serif;font-size:15px;letter-spacing:.08em}}
.wrap{{max-width:760px;margin:0 auto;padding:24px 20px 60px}}
h1{{font-family:'Cinzel',serif;font-size:26px;margin-bottom:18px}}
ul{{list-style:none;columns:2;column-gap:30px}}
@media(max-width:560px){{ul{{columns:1}}}}
li{{break-inside:avoid;padding:5px 0;border-bottom:.5px solid rgba(176,144,96,.3)}}
li a{{color:#8b3a1a;text-decoration:none;font-size:16px}}
li span{{display:block;font-size:12px;font-style:italic;color:#5c4a2a}}
</style></head>
<body>
<header><a href="{BASE}/">&#10022; Folklore Map of the British Isles &#10022;</a></header>
<div class="wrap"><h1>All Legends ({written})</h1><ul>
{items}
</ul></div></body></html>"""
    with io.open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # sitemap.xml
    today = datetime.date.today().isoformat()
    urls = [f"{BASE}/", f"{BASE}/{OUT_DIR}/"]
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
