# -*- coding: utf-8 -*-
"""
sourcing_audit.py — the recurring sourcing-pass tool referenced in the
editorial policy (/editorial): "entries are periodically revisited so
sourcing can be upgraded as better material becomes available."

Re-checks every entry in legends.json against the same SOURCE_TIERS
reliability ranking generate_pages.py uses to render each entry's Sources
list, and flags anything worth a second look. Run it periodically (there's
no fixed schedule enforced — it's a manual editorial pass) as new sources
get added to SOURCE_TIERS or new legends are researched:

    python sourcing_audit.py

Writes sourcing_audit_report.json (flagged entries, sorted worst-first) and
prints a human-readable summary. Doesn't modify legends.json or touch any
generated page — it's read-only, for editorial triage.
"""
import json
import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass  # Python <3.7 fallback: console output may mis-render accented names.

from generate_pages import legend_sources

STRONG_TIERS = {"primary", "heritage", "encyclopedic"}


def severity_for(sources):
    """(severity_rank, reason) — lower rank is worse, sorts flagged entries
    worst-first. None means the entry doesn't need flagging."""
    if not sources:
        return 0, "no sources listed"
    tiers = [s["tier"] for s in sources]
    if not any(tiers):
        return 1, "no source could be classified by reliability tier"
    if not any(t in STRONG_TIERS for t in tiers):
        return 2, "only secondary/popular sources, no primary or heritage record"
    if len(sources) == 1:
        return 3, "only a single source"
    if None in tiers:
        return 4, "at least one source has an unrecognised host (add it to SOURCE_TIERS)"
    return None, None


def main():
    with io.open("legends.json", encoding="utf-8") as f:
        data = json.load(f)
    legends = data.get("legends", [])

    flagged = []
    for leg in legends:
        sources = legend_sources(leg)
        rank, reason = severity_for(sources)
        if rank is None:
            continue
        flagged.append({
            "name": leg["name"],
            "severity_rank": rank,
            "reason": reason,
            "source_count": len(sources),
            "tiers": [s["tier"] or "unclassified" for s in sources],
            "urls": [s["url"] for s in sources],
        })

    flagged.sort(key=lambda f: (f["severity_rank"], f["name"]))

    with io.open("sourcing_audit_report.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated": True,
            "total_legends": len(legends),
            "flagged_count": len(flagged),
            "flagged": flagged,
        }, f, ensure_ascii=False, indent=2)

    by_rank = {}
    for f in flagged:
        by_rank.setdefault(f["severity_rank"], []).append(f)

    labels = {
        0: "No sources at all",
        1: "Sources present but none classifiable",
        2: "Only secondary/popular sources (no primary or heritage record)",
        3: "Only a single source",
        4: "Has an unrecognised source host",
    }
    print(f"Checked {len(legends)} legends — {len(flagged)} flagged for a sourcing review.\n")
    for rank in sorted(by_rank):
        items = by_rank[rank]
        print(f"[{rank}] {labels[rank]} — {len(items)} entr{'y' if len(items) == 1 else 'ies'}")
        for item in items[:10]:
            print(f"      - {item['name']}")
        if len(items) > 10:
            print(f"      ... and {len(items) - 10} more")
        print()
    print("Full detail written to sourcing_audit_report.json")


if __name__ == "__main__":
    main()
