# Folklore Map

The website reads legends from Supabase first and falls back to `legends.json`
when Supabase cannot be reached. The JSON file is also the reviewed local
backup used for database updates.

## Setup

Install the Python dependency:

```powershell
python -m pip install -r requirements.txt
```

Set the private Supabase service-role key in the terminal session used for
updates. Do not commit this key or add it to `index.html`.

```powershell
$env:SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
$env:SUPABASE_SERVICE_KEY = "YOUR_SERVICE_ROLE_KEY"
```

For Command Prompt, do not include quotes in the stored values:

```bat
set SUPABASE_URL=https://YOUR_PROJECT.supabase.co
set SUPABASE_SERVICE_KEY=YOUR_SERVICE_ROLE_KEY
```

## Supabase Schema

The `legends` table mirrors the fields in `legends.json`:

| Column       | Type        | Notes                                              |
|--------------|-------------|----------------------------------------------------|
| `name`       | `text`      | Unique, used as the upsert conflict key            |
| `lat`, `lng` | `float8`    |                                                      |
| `category`   | `text`      | Defaults to `beast`                                |
| `region`     | `text`      | Defaults to `Britain`                              |
| `summary`    | `text`      | Short description shown on the map                |
| `source`     | `text`      | Primary citation URL (also the map popup's link)   |
| `detail`     | `text`      | Optional long-form write-up; `null` when absent    |
| `tags`       | `text[]`    | Thematic/region tags; empty array when absent      |
| `date_added` | `date`      | `null` for older records without a recorded date   |

### Multiple sources (`sources`)

Beyond the single `source` URL, an entry in `seeds.json`/`legends.json` may
carry an optional `sources` array for richer, classified sourcing — rendered on
the static legend page as a labelled list and emitted as multiple `isBasedOn`
citations in the JSON-LD. It lives in the JSON only (not a Supabase column); the
map still uses the single `source`. Each item is a URL string or an object:

```json
"sources": [
  { "url": "https://www.duchas.ie/...", "type": "primary", "publisher": "Dúchas" },
  { "url": "https://en.wikipedia.org/wiki/...", "type": "encyclopedic" }
]
```

`type` is one of `primary | heritage | secondary | encyclopedic | popular`
(shown as a small label). When `type`/`publisher` are omitted, the generator
infers a publisher name from the host and a tier from a known-host map
(`SOURCE_TIERS` in `generate_pages.py`), showing no label when unsure. List the
strongest source first.

### Pronunciation (`pronunciation`)

An optional short phonetic hint for legend names that are non-obvious to an
English reader (Welsh, Irish, Scottish Gaelic, Manx, etc.) — e.g. `"koon
AN-oon"` for Cŵn Annwn. Rendered as a small line under the legend page's
title, and omitted entirely when absent (most entries won't have one). Like
`sources`, it lives in the JSON only (not a Supabase column) — the map doesn't
need it. **Only add a pronunciation backed by a real source you checked**
(Forvo, Wiktionary IPA, a BBC/heritage-body guide, etc.) — never a best guess
from the spelling; leave the field unset rather than guess.

Migrations live in `supabase/migrations/`. The `detail`, `tags` and
`date_added` columns were added by
`supabase/migrations/20260612160000_add_legend_detail_tags_date_added.sql`
(nullable, safe to re-run via `add column if not exists`).

`map.html` only requests `name,lat,lng,category,region,summary,source` from
Supabase — `detail`, `tags` and `date_added` are stored for future use but
deliberately excluded from the map's initial data load to keep it small.

## Image-Led Legend Pages

All legend records use the redesigned editorial layout and mini-map. Entries
without completed artwork show a category-based placeholder. The placeholder
is replaced automatically when a compressed hero image and editorial metadata
are added to `legend_pages.json`.

Before generating or replacing artwork, follow the preflight, composition,
variety, and non-overwrite rules in [PHOTOGRAPHY_STANDARDS.md](PHOTOGRAPHY_STANDARDS.md).

Add the hero image under `legend-images/`, add the matching legend name to the
manifest, then regenerate the static pages:

```powershell
python generate_pages.py
```

The shared layout and map behaviour live in `legend-page.css` and
`legend-page.js`. Do not edit generated files under `legends/` directly.

**Editor's note (optional).** Any legend can carry a short, named editorial
aside — a deliberate human-voice signal explaining why the legend was chosen or
adding curator commentary. Add `editorial` (and optionally `editorial_by`, which
defaults to "Folklore Map editors") to the legend's entry in `legend_pages.json`,
or set the same fields directly on a seed in `seeds.json`. It renders as an
"Editor's note" block in the article and is omitted entirely when unset.

**Nearby legends** are generated automatically on every page from the four
geographically closest entries (haversine distance, within 200 km) — no manual
data needed.

## Clean Database Sync

Use this after reviewing local seed and JSON changes:

```powershell
python build_legends.py --seed-only --supabase --supabase-prune
```

This preserves the reviewed local dataset, upserts it to Supabase, and deletes
remote rows that are absent from the reviewed local dataset.

Run without `--supabase-prune` when you want an additive update that leaves
existing remote-only rows untouched.

## Expand And Review The Dataset

Run the Wikipedia refresh into a separate review file first:

```powershell
python build_legends.py --output legends.wikipedia-review.json --verbose
```

This includes pirate, privateer, smuggler and maritime folklore discovery. It
leaves the reviewed `legends.json` backup and Supabase database unchanged.

Pirate biographies are curated rather than imported wholesale. The map keeps
figures with a clear legendary, ballad, treasure-lore or local-tradition link;
ordinary historical privateers remain review candidates.

Heritage services are useful for finding candidates, but their records are not
proof of a folklore connection. Run them into a separate file for manual
review:

```powershell
python build_legends.py --hes --historic-england --dbpedia --output legends.heritage-review.json --verbose
```

After reviewing the new records, replace `legends.json` with the approved
review file and run the clean database sync command above.

## One-Off Source Snapshots

For broader research expansion, create a stored metadata snapshot of the
requested public sources:

```powershell
python snapshot_expansion_sources.py
```

The snapshot tool checks public crawl rules, stores titles, URLs and short
excerpts under `source_snapshots/one_off_expansion/`, and writes a combined
`review_candidates.json` plus a `manifest.json` recording source outcomes. It
does not change `legends.json` or Supabase.

The stored snapshot is intended for one-off review so the project does not
need to repeatedly query external sites. Full copyrighted articles are not
mirrored.

Create a separate Encyclopedia.com folklore snapshot and deduplicated review
file with:

```powershell
python snapshot_expansion_sources.py --source encyclopedia_com
```

This compares Encyclopedia.com metadata against the current `legends.json`
names and writes `encyclopedia_com_review_candidates.json` without replacing
the earlier combined candidate report.

## Search Console Insights

`fetch_search_insights.py` pulls Google Search Console performance data and
writes a short, prioritised report (`search-insights/report.md`) the daily
research/QC work can act on: pages to retitle (high impressions, low CTR),
pages ranking just off page 1, search terms not yet covered, and zero-click
queries. It stores only aggregate query/page metrics — no visitor data — and
`search-insights/` plus the service-account key are git-ignored.

One-time setup (Google service account, read-only):

1. In Google Cloud, create a project, create a service account, and download
   its JSON key. Enable the "Google Search Console API" for the project.
2. In Search Console → Settings → Users and permissions, add the service
   account's email as a **Restricted** user on the property.
3. Save the key as `gsc-service-account.json` in the repo root (git-ignored),
   or point `GSC_SERVICE_ACCOUNT_JSON` at it. Set `GSC_SITE_URL` if the
   property is not the default `https://folklorefinder.uk/` (use
   `sc-domain:folklorefinder.uk` for a domain property).

```powershell
python fetch_search_insights.py            # fetch and write the report
python fetch_search_insights.py --sample   # preview the report format, no credentials
```

Run it on a cadence (monthly is plenty at current traffic) and have the
research step read `search-insights/report.md` when choosing priorities.
