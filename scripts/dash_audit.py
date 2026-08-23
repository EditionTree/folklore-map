#!/usr/bin/env python3
"""Report em/en-dashes remaining in the legend dataset's prose fields.

Why this exists: the "no em dashes" rule in content-style-guide.md has been
declared done twice (2026-08-07 and 2026-08-12) and been wrong both times,
because a scoped pass over some pages was reported as a pass over the dataset.
A rule nobody can check is a rule that quietly rots. This makes the claim
falsifiable in one command.

    python scripts/dash_audit.py            # summary
    python scripts/dash_audit.py --list     # every offending value
    python scripts/dash_audit.py --field summary --list
    python scripts/dash_audit.py --strict   # exit 1 if any PROSE dash remains

Numeric ranges ("1560s-1576", "c. 1196-98", "AD 60-61") are counted separately
and are NOT failures: a range wants a hyphen, not deletion, and rewriting one
into a sentence would be worse than leaving it. Everything else is prose and
has to be restructured by hand, per the rule's own preference order
(full stop, then comma, then parentheses, and a colon only for a real list).

Generated HTML is deliberately not scanned. legends.json is the source; the
pages are downstream of it, so fixing a page without fixing the entry means the
next `python generate_pages.py` puts the dash straight back.
"""

import argparse
import io
import json
import os
import re
import sys

DASH = re.compile(r"[—–]")

# A dash sitting between two digits is doing range duty. Allow an optional
# apostrophe-decade ("1560s-1576") and a trailing letter-free year fragment.
RANGE = re.compile(r"\d\s*[—–]\s*\d")

# Prose fields, in the order a reader meets them on the page. `name`, `region`
# and the slug fields are excluded: they are identifiers, not copy.
FIELDS = [
    "summary",
    "detail",
    "earliest_record",
    "historical_setting",
    "period",
    "cultural_tradition",
    "origin_date",
]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_legends():
    path = os.path.join(REPO, "legends.json")
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("legends", data)


def audit(legends, fields):
    """-> {field: {"prose": [(name, value)], "range": [(name, value)]}}"""
    out = {f: {"prose": [], "range": []} for f in fields}
    for leg in legends:
        name = leg.get("name", "?")
        for f in fields:
            v = leg.get(f)
            if not isinstance(v, str) or not DASH.search(v):
                continue
            # A value can hold both a range and a prose dash. Strip the ranges
            # first; if a dash survives that, the value still needs editing.
            stripped = RANGE.sub("", v)
            bucket = "prose" if DASH.search(stripped) else "range"
            out[f][bucket].append((name, v))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print every offending value")
    ap.add_argument("--field", action="append", choices=FIELDS,
                    help="restrict to one field (repeatable)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any prose dash remains")
    args = ap.parse_args()

    fields = args.field or FIELDS
    legends = load_legends()
    result = audit(legends, fields)

    prose_total = sum(len(result[f]["prose"]) for f in fields)
    range_total = sum(len(result[f]["range"]) for f in fields)
    entries = {n for f in fields for n, _ in result[f]["prose"]}

    print(f"legends.json: {len(legends)} entries, {len(fields)} prose fields scanned")
    print()
    print(f"  {'field':22} {'prose':>7} {'range':>7}")
    print(f"  {'-' * 22} {'-' * 7} {'-' * 7}")
    for f in fields:
        p, r = len(result[f]["prose"]), len(result[f]["range"])
        flag = "  <-- fix" if p else ""
        print(f"  {f:22} {p:>7} {r:>7}{flag}")
    print(f"  {'-' * 22} {'-' * 7} {'-' * 7}")
    print(f"  {'TOTAL':22} {prose_total:>7} {range_total:>7}")
    print()
    print(f"{prose_total} prose dashes to rewrite, across {len(entries)} entries.")
    print(f"{range_total} numeric ranges left alone (a range wants a hyphen, not a rewrite).")

    if args.list:
        for f in fields:
            if not result[f]["prose"]:
                continue
            print()
            print(f"=== {f} ({len(result[f]['prose'])}) ===")
            for name, v in result[f]["prose"]:
                for m in DASH.finditer(v):
                    ctx = " ".join(v[max(0, m.start() - 55):m.end() + 55].split())
                    print(f"  [{name}] ...{ctx}...")

    if args.strict and prose_total:
        print()
        print(f"FAIL: {prose_total} prose dashes remain.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
