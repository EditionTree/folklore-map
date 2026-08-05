# /research-folklore

Conduct a British and Irish folklore research session and write a dated JSON review report to `source_snapshots/research_queue/`.

This skill only finds and proposes brand-new candidate legends. The daily
scheduled task at `C:\Users\Greg\.claude\scheduled-tasks\research-folklore-weekly\SKILL.md`
does that AND a full enrichment pass (dating, sourcing, no-ai-slop-checked
summary rewrites) on existing entries each run — see that file for the
current, actually-running version of this workflow.

## Trigger

User types `/research-folklore` or asks to run a folklore research session.

## Constraints (hard rules — never violate)

- **Never** edit `legends.json`, `build_legends.py`, or `index.html`.
- **Never** write outside `source_snapshots/research_queue/`.
- **Never** update Supabase, commit changes, push to GitHub, or open a pull request.
- **Never** add entries solely to inflate the count. Quality over quantity.
- Output file: `source_snapshots/research_queue/YYYY-MM-DD_research.json` (today's date).

## Research priorities (in order)

1. **Irish** — regional traditions from Ulster, Leinster, Munster, Connacht; both Northern Ireland and the Republic. **Northern Ireland is currently under-represented (only 9 of 539 entries tagged `northern-ireland`)** — actively seek named traditions from Antrim, Armagh, Down, Fermanagh, Londonderry/Derry, and Tyrone.
2. **Scottish islands** — Hebrides (Skye, Islay, Mull, Colonsay, etc.), Orkney, Shetland, Arran, smaller islands.
3. **Welsh local legends** — specific villages, lakes, mountains, ruins, coastal sites.
4. **English county traditions** — named local legends, underrepresented counties preferred.
5. **Achievement-driven targets** (gamification feature in development — see `_drafts/achievements.md`):
   - **"Black dog" apparitions** — British/Irish spectral black dog legends (in the vein of Black Shuck, Barghest, Padfoot, Wulver, Cù Sìth, Gwyllgi, Church Grim, Black Dog of Newgate, Black Dog of Bouley Bay — these 9 already exist). One or two more strong, distinct named black-dog legends would unlock a "10 black dogs" achievement tier. Reject if it's just a regional rename of an existing one (near-duplicate check applies as normal).
   - **Maid Marian** — currently has no standalone entry despite Robin Hood, King Arthur, and other Matter-of-Britain figures being present. If a genuine folkloric tradition (not just literary/film history) can be sourced with a defensible map pin, add as a strong candidate.
6. **Category balance (tiebreaker)** — see Step 1a. When a candidate could reasonably fit more than one category, or when choosing between otherwise-equal candidates, prefer the one in a currently under-represented category.

## Per-run workflow

### Step 1 — Load existing names

Read `legends.json`. Extract all `name` values. Keep this list in memory for duplicate checking throughout the run.

### Step 1a — Check category balance

Count entries per `category` value in `legends.json`. Note the 3 categories with the lowest counts (as of the last run: Giants, Pirates, Dragons — but recompute each time, don't rely on this). Keep this list as a soft tiebreaker for Step 2/5 — it does not override priorities 1-5, but when a genuinely strong candidate could fit one of these under-represented categories, favour including it.

### Step 2 — Research

Search reputable sources for folklore candidates across all four priority areas. Aim for balance: at least two strong candidates per priority area where evidence supports it. Target 8–16 strong candidates total. Where a strong candidate naturally fits one of the under-represented categories noted in Step 1a, give it a slight edge when deciding what to include.

**Preferred sources:**
- Wikipedia articles with folklore/mythology categories
- Irish Folklore Commission digitised material (duchas.ie, folklore.ie)
- Schools' Collection (dúchas.ie)
- Canmore (Historic Environment Scotland)
- Coflein (Welsh heritage database)
- Historic England listed entries with folklore notes
- JSTOR / academic articles on regional folklore
- Published folklore society journals
- Books by reputable folklore scholars (e.g. Katharine Briggs, Dáithí Ó hÓgáin, John Rhys)

**Reject outright:**
- Generic history pages with no folkloric tradition
- Ordinary heritage sites / listed buildings without a legend
- Biographies of historical figures unless a named folkloric tradition attaches to them
- Entries without at least one defensible map pin in the British Isles
- Unsupported claims from personal blogs or unverified sites
- Anything that duplicates or near-duplicates an existing legend

### Step 3 — Duplicate check

For each candidate:
- Exact name match against existing legends → reject as duplicate.
- Near-duplicate check: similar name (variant spelling, translation, alias) or same location + same creature type → flag as `"duplicate_check": "possible near-duplicate of <Name>"`.
- No match → `"duplicate_check": "none found"`.

### Step 3a — Sourcing (capture for every candidate)

Populate the `sources` list, not just a single link. Aim for **at least two
sources where the evidence supports it**, and prefer at least one stronger than
an encyclopedia:

- `primary` — original folklore record/archive (Dúchas/National Folklore Collection, a 19th-c. folklorist's text on Project Gutenberg, an original collection)
- `heritage` — heritage record (Historic England, Canmore, National Trust, a museum)
- `secondary` — scholarly or folklore-society secondary writing
- `encyclopedic` — Wikipedia, Oxford Reference
- `popular` — tourism sites, regional blogs, general-interest pieces

List the strongest source first. A single encyclopedic/popular source is still
acceptable for a `medium` candidate, but a corroborating primary/heritage source
raises confidence. Set `publisher` only when the friendly name isn't obvious
from the domain.

### Step 4 — Score confidence

| Level | Criteria |
|-------|----------|
| `high` | Named tradition, reliable academic/heritage source, clear map pin |
| `medium` | Named tradition, plausible source, map pin resolvable to region |
| `low` | Interesting but source quality uncertain or location vague |

Reject `low`-confidence entries unless exceptionally notable.

### Step 5 — Categorise

Use only the existing category keys: `beast`, `ghost`, `fairy`, `water`, `dragon`, `witch`, `deity`, `giant`, `location`, `hero`, `pirate`.

### Step 6 — Write report

Write `source_snapshots/research_queue/YYYY-MM-DD_research.json` with the structure below. Do not touch any other file.

## Output JSON schema

```json
{
  "generated": "<ISO-8601 timestamp>",
  "run_date": "<YYYY-MM-DD>",
  "strong_candidates": [
    {
      "name": "string",
      "category": "one of the 11 keys",
      "region": "Named region, Country",
      "priority_group": 1,
      "lat": 0.0,
      "lng": 0.0,
      "summary": "2–4 sentence folklore summary",
      "evidence_links": ["url1", "url2"],
      "sources": [
        { "url": "url", "type": "primary | secondary | heritage | encyclopedic | popular", "publisher": "optional human-readable name, e.g. Dúchas, Historic England" }
      ],
      "confidence": "high | medium",
      "duplicate_check": "none found | possible near-duplicate of <Name>",
      "editorial_notes": "Researcher notes: source quality, caveats, suggested edits"
    }
  ],
  "uncertain_candidates": [
    {
      "name": "string",
      "category": "string",
      "region": "string",
      "priority_group": 1,
      "lat": 0.0,
      "lng": 0.0,
      "summary": "string",
      "evidence_links": ["url"],
      "confidence": "medium | low",
      "duplicate_check": "string",
      "editorial_notes": "Why uncertain; what additional verification would help"
    }
  ],
  "rejected": [
    {
      "name": "string",
      "reason": "short reason (e.g. 'generic history page', 'no folkloric tradition', 'duplicate of Banshee')"
    }
  ],
  "run_summary": {
    "strong_count": 0,
    "uncertain_count": 0,
    "rejected_count": 0,
    "priority_coverage": {
      "1_irish": 0,
      "2_scottish_islands": 0,
      "3_welsh": 0,
      "4_english": 0
    },
    "underrepresented_categories_targeted": ["category keys from Step 1a that strong_candidates fall into"],
    "notes": "Researcher notes on this run: gaps, sources used, suggestions for future runs"
  }
}
```

## After writing the file

Report to the user:
- The output file path.
- Count of strong / uncertain / rejected candidates.
- Priority coverage breakdown.
- Any near-duplicates flagged.
- Reminder that `legends.json` has not been touched and all decisions are for manual review.
