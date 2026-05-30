#!/usr/bin/env python3
"""
enrich_legends.py — Clean up legends.json and enrich summaries via Claude API

Does three things in order:
  1. Fixes category mismatches (maps ancient_site→location, hero→deity etc.)
  2. Removes duplicates and purely geographic non-folklore entries
  3. Rewrites all summaries via Claude API in an atmospheric folklore voice

Usage:
    python enrich_legends.py --api-key YOUR_ANTHROPIC_KEY
    python enrich_legends.py --api-key YOUR_KEY --dry-run   (preview without writing)
    python enrich_legends.py --api-key YOUR_KEY --skip-enrichment  (just clean)
"""

import argparse
import json
import time
import requests
from copy import deepcopy


ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL         = "claude-sonnet-4-20250514"
RATE_LIMIT    = 0.5   # seconds between API calls


# ---------------------------------------------------------------------------
# Category remapping — maps seed categories to map-known categories
# ---------------------------------------------------------------------------
CATEGORY_REMAP = {
    "ancient_site": "location",   # stone circles, hillforts etc → sacred site
    # "hero" is now a valid category — no remap needed
    "ritual":       "location",   # festivals and rituals tied to places
    "norse":        "deity",      # Norse figures → deity
}

# All valid map categories after remapping
VALID_CATEGORIES = {
    "beast", "ghost", "fairy", "water", "dragon",
    "witch", "deity", "giant", "location", "hero"
}

# ---------------------------------------------------------------------------
# Entries to remove — not folklore, purely geographic, duplicates, or
# outside the UK bounding box. Reviewed entry by entry.
# ---------------------------------------------------------------------------
REMOVE_ENTRIES = {
    # Not folklore — organisations, institutions
    "Cardiff University",
    "English Folk Dance and Song Society",
    "School of Scottish Studies",
    # Not folklore — military/modern
    "SM UB-85",
    "Battle of Britain Memorial, Capel-le-Ferne",
    "Bulford Kiwi",
    "Barns of Ayr",
    "Lancashire Witches Walk",
    # Not folklore — purely geographic
    "River Tamar",
    "Loch Linnhe",
    "Black Rock Gorge",
    "Beinn a' Bheithir",
    "Kitterland",
    # Not folklore — towns/villages with no meaningful folklore content
    "Kirriemuir",
    "Whitehawk",
    "Witchknowe Park",
    "Morrison's Haven",
    "Smeaton House",
    "Gatton Park",
    # Not folklore — hill figures with no legend attached
    "Osmington White Horse",         # depicts King George III, no folklore
    "Folkestone White Horse",         # modern, no folklore
    "Watlington White Mark",          # geometric mark, no folklore
    "Whiteleaf Cross",                # chalk cross, disputed origin, no legend
    "Lenham Cross",                   # WW2 memorial chalk cross
    # Not folklore — general archaeology, no legend
    "Spong Hill",
    # Outside UK — Ireland
    "Fintan's Grave",
    "Lia Fáil",
    "Mag Lena",
    "Latoon Fairy Bush",
    "Latoon fairy bush",
    # Previously identified removals retained
    "Four Ashes, Buckinghamshire",
    "Harrow on the Hill",
    "Kirkharle",
    "Thundersley",
    "Thursley",
    "Wednesbury",
    "Weedon Lois",
    "Weeley",
    "Wing, Buckinghamshire",
    "Woodnesborough",
    "Wye, Kent",
    "Lenham",
    "Fovant Badges",
    "Shoreham Memorial Cross",
    "Porthchapel Beach",
    "St Anthony-in-Meneage",
    "White Lion Inn, Stratford-upon-Avon",
    "Kirkcudbright Tolbooth",
    "Keith Marischal",
    "Innerwick Castle",
    "Canewdon",
    "Crook of Devon",
    "Museum of Witchcraft and Magic",
    "Overtoun Bridge",               # dogs jumping off bridge — urban legend, not folklore
    # Duplicates — keep the better-named version
    "Enfield poltergeist",           # keep "Enfield Poltergeist"
    "The Giant of Cerne Abbas",      # keep "Cerne Abbas Giant"
    "The Long Man of Wilmington",    # keep "Long Man of Wilmington"
    "Witches' Well, Edinburgh",      # keep "Witches' Well"
    "Fairy Bridge (Isle of Man)",    # keep "Fairy Bridge"
    "Nine Maidens stone row",        # keep "Nine Maidens Stone Row"
    "Stanton Drew stone circles",    # keep "Stanton Drew Stone Circles"
    "Whetstones",                    # keep "Whetstones (stone circle)"
    "The Giant's Causeway",          # keep "Giant's Causeway"
    # Ireland — remove entries outside British Isles scope or pure geography
    "Fintan's Grave",                # Irish mountain, no folklore content
    "Mag Lena",                      # Irish plain, no folklore content
    "Latoon Fairy Bush",             # keep but coords are in Ireland — fine
    "Latoon fairy bush",             # duplicate capitalisation
}

# ---------------------------------------------------------------------------
# Force category corrections — reviewed entry by entry
# ---------------------------------------------------------------------------
FORCE_CATEGORY = {
    # Giants
    "Gogmagog":               "giant",
    "Rhitta Gawr":            "giant",
    "Bran the Blessed":       "giant",
    "Cerne Abbas Giant":      "giant",
    "Giant's Causeway":       "giant",
    # Deities / heroes
    # Ghosts / spirits
    "Redcap":                 "ghost",    # murderous goblin spirit, not a beast
    "The Black Dog of Newgate": "ghost",  # haunting, not a creature
    "Cock Lane ghost":        "ghost",
    # Water
    "Nanny Rutt":             "water",    # spirit of a well/spring
    # Locations
    "Maeshowe Runes":         "location",
    "Orkneyinga Saga":        "location",
    "Beltane Fire Festival":  "location",
    "Hobby Horse of Padstow": "location",
    "Mari Lwyd":              "location",
    "Up Helly Aa":            "location",
    "Cheetham Close":         "location",
    "Craddock Moor stone circle": "location",
    "Bryn Cader Faner":       "location",
    "Bryn Gwyn stones":       "location",
    "Nine Maidens Stone Row":  "location",
    "Stanton Drew Stone Circles": "location",
    "Whetstones (stone circle)": "location",
    "St Trinian's Church":    "location",
    "Cock Lane ghost":        "ghost",
    "Cantre'r Gwaelod":       "location",  # drowned kingdom, not a deity
    "Battle of Barry":        "location",  # legendary battle site
    "Lochmaben Stone":        "location",  # megalith linked to deity
    "Towednack":              "location",  # Cornish village with folklore
    "Caer Bran":              "location",
    "Zennor":                 "location",  # village famous for mermaid legend
    "Trow":                   "fairy",
    # Irish entries
    "Banshee":                "ghost",
    "Pooka":                  "fairy",
    "Aos Sí":                 "fairy",
    "Cú Chulainn":            "deity",
    "Fionn mac Cumhaill":     "deity",
    "The Dagda":              "deity",
    "Tuatha Dé Danann":       "deity",
    "Balor of the Evil Eye":  "giant",
    "Queen Medb":             "deity",
    "Cailleach Bhéara":       "deity",
    "Children of Lir":        "deity",
    "Newgrange":              "location",
    "Hill of Tara":           "location",
    "Croagh Patrick":         "location",
    "Knocknarea":             "location",
    "Giant's Causeway":       "giant",
    "Salmon of Knowledge":    "water",
    # New British entries
    "Black Annis":            "beast",
    "Wisht Hounds":           "beast",
    "Blue Men of the Minch":  "water",
    "Blodeuwedd":             "deity",
    "Gwyn ap Nudd":           "deity",
    "Merlin":                 "deity",
    "Gog and Magog":          "giant",
    "Camelot":                "location",
    "Avalon":                 "location",
    "Hafren":                 "deity",
    "Gwy":                    "deity",
    "Rheidol":                "deity",
    "Plynlimon":              "giant",
    "Elder Mother":           "deity",
    "Mother Ludlam":          "witch",
    "Helen Duncan":           "witch",
    "Yallery Brown":          "fairy",
    "Seelie Court":           "fairy",
    "Unseelie Court":         "fairy",
    "Tylwyth Teg":            "fairy",
    "Glaistig":               "water",
    "Bean Nighe":             "ghost",
    "Filey Dragon":           "dragon",
    "Gurt Worm":              "dragon",
    "Mordiford Dragon":       "dragon",
    "Penhill Giant":          "giant",
    "Dick Turpin":            "ghost",
    "Lantern Man":            "ghost",
    "Renwick Cockatrice":     "beast",
    "Pixie":                  "fairy",
    "Boggarts":               "fairy",
    "Brown Man of the Muirs": "fairy",
    "Gooseberry Wife":        "fairy",
    "Hyter Sprite":           "fairy",
    "Wights":                 "ghost",
    # Heroic Figures — mortals defined by deeds not domains
    "Lancelot":               "hero",
    "Gawain":                 "hero",
    "Beowulf":                "hero",
    "The Green Knight":       "hero",
    "Corineus":               "hero",
    "Cú Chulainn":            "hero",
    "Fionn mac Cumhaill":     "hero",
    "Boudicca":               "hero",
    "Fingal":                 "hero",
    "Wayland the Smith":      "hero",
    "Dunstan and the Devil":  "hero",
    "Dick Turpin":            "hero",
    "Helen Duncan":           "hero",
}

# ---------------------------------------------------------------------------
# Claude API enrichment
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are writing entries for an atmospheric interactive folklore map of Britain.
Your task is to rewrite Wikipedia summaries into evocative, one-paragraph descriptions
in the style of an old folklore almanac or bestiary — mysterious, vivid, and specific.

Rules:
- 2-4 sentences maximum
- Use present tense where it adds atmosphere ("it is said", "locals claim", "the creature haunts")
- Include the most interesting/unusual detail from the original
- Never start with "This is" or the entry's name as the first word
- No modern academic language — write as if from an old book
- Keep factual accuracy — don't invent details not in the original
- For location entries, emphasise the mythic/folkloric significance of the place
- For deity entries, capture their power and domain
- Keep it under 300 characters if possible — these are popup summaries"""


def enrich_summary(name: str, category: str, original_summary: str, api_key: str) -> str:
    """Call Claude API to rewrite a summary in atmospheric folklore voice."""
    prompt = f"""Rewrite this as an atmospheric folklore almanac entry (2-4 sentences, under 300 characters ideally):

Entry name: {name}
Category: {category}
Original text: {original_summary}

Write only the rewritten summary, nothing else."""

    try:
        response = requests.post(
            ANTHROPIC_API,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": MODEL,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["content"][0]["text"].strip()

    except requests.exceptions.HTTPError as e:
        print(f"    [!] API error for '{name}': {e}")
        return original_summary
    except Exception as e:
        print(f"    [!] Unexpected error for '{name}': {e}")
        return original_summary


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def clean_and_enrich(api_key: str, skip_enrichment: bool, dry_run: bool, verbose: bool):
    print("\n  Folklore Map — cleanup & enrichment pipeline")
    print("  " + "─" * 46)

    with open("legends.json", encoding="utf-8") as f:
        data = json.load(f)

    legends = data["legends"]
    print(f"\n  Input: {len(legends)} legends")

    # ── Step 1: Remove unwanted entries ──────────────────────────────────
    before = len(legends)
    legends = [l for l in legends if l["name"] not in REMOVE_ENTRIES]
    removed = before - len(legends)
    print(f"\n  [1/3] Removed {removed} non-folklore/duplicate entries")

    # ── Step 2: Fix categories ────────────────────────────────────────────
    fixed_cat = 0
    for leg in legends:
        original = leg["category"]

        # Apply force-corrections first
        if leg["name"] in FORCE_CATEGORY:
            leg["category"] = FORCE_CATEGORY[leg["name"]]

        # Then apply remapping
        if leg["category"] in CATEGORY_REMAP:
            leg["category"] = CATEGORY_REMAP[leg["category"]]

        # Fallback for anything still unknown
        if leg["category"] not in VALID_CATEGORIES:
            leg["category"] = "beast"

        if leg["category"] != original:
            fixed_cat += 1
            if verbose:
                print(f"    {leg['name']}: {original} → {leg['category']}")

    print(f"  [2/3] Fixed {fixed_cat} category assignments")

    # Category breakdown
    from collections import Counter
    cats = Counter(l["category"] for l in legends)
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"         {cat}: {count}")

    # ── Step 3: Claude API enrichment ────────────────────────────────────
    if skip_enrichment:
        print(f"\n  [3/3] Skipped enrichment (--skip-enrichment)")
    elif not api_key:
        print(f"\n  [3/3] Skipped enrichment (no --api-key provided)")
    else:
        print(f"\n  [3/3] Enriching {len(legends)} summaries via Claude API ...")
        print(f"         This will take approximately {len(legends) * RATE_LIMIT / 60:.1f} minutes")

        enriched = 0
        errors   = 0

        for i, leg in enumerate(legends, 1):
            if verbose:
                print(f"    [{i}/{len(legends)}] {leg['name']}")
            else:
                # Progress indicator every 10 entries
                if i % 10 == 0:
                    print(f"         {i}/{len(legends)} done ...")

            new_summary = enrich_summary(
                leg["name"],
                leg["category"],
                leg.get("summary", ""),
                api_key
            )

            if new_summary != leg.get("summary", ""):
                leg["summary"] = new_summary
                enriched += 1
            else:
                errors += 1

            time.sleep(RATE_LIMIT)

        print(f"         Enriched: {enriched} | Unchanged/errors: {errors}")

    # ── Write output ──────────────────────────────────────────────────────
    if dry_run:
        print(f"\n  Dry run — not writing. Would output {len(legends)} legends.")
        return

    from datetime import datetime, timezone
    data["legends"]   = sorted(legends, key=lambda x: x["name"])
    data["total"]     = len(legends)
    data["generated"] = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

    with open("legends.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n  Done — {len(legends)} legends written to legends.json\n")


def main():
    parser = argparse.ArgumentParser(description="Folklore Map — cleanup & enrichment")
    parser.add_argument("--api-key",          default="",           help="Anthropic API key")
    parser.add_argument("--skip-enrichment",  action="store_true",  help="Just clean, skip Claude API")
    parser.add_argument("--dry-run",          action="store_true",  help="Preview changes without writing")
    parser.add_argument("--verbose", "-v",    action="store_true",  help="Show each change")
    args = parser.parse_args()
    clean_and_enrich(args.api_key, args.skip_enrichment, args.dry_run, args.verbose)


if __name__ == "__main__":
    main()
