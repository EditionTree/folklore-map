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
