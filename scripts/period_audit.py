#!/usr/bin/env python3
"""Report Explore Through Time coverage: controlled `period_slug` vs the bridge.

Why this exists: `period` is 626 distinct free-text values across 710 entries,
and it mixes two different facts in one field. Some values say when the legend
is SET ("Restoration England, 17th century"), some say when it was RECORDED
("First published 1865"), and 289 say both in one sentence. A period page can
only mean one of those, and it means the first: see periods.json's `_comment`
and content-style-guide.md under "Assigning period_slug".

`period_slug` is the controlled answer. This script says how far it has got,
which entries still lean on the free-text bridge in generate_pages.py, and
whether anything carries a slug that is not in periods.json.

    python scripts/period_audit.py              # coverage table
    python scripts/period_audit.py --bridged    # entries still on the bridge
    python scripts/period_audit.py --list victorian-britain
    python scripts/period_audit.py --strict     # exit 1 on an invalid slug

--strict fails ONLY on an invalid slug. Thin or empty pages are not failures:
the fifteen periods are a fixed historical framework, and a page fills when the
enrichment pass finds entries that honestly belong on it, not before.
"""

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    return json.load(io.open(os.path.join(ROOT, name), encoding="utf-8"))


def bridge_slug(value, periods_by_title, match_terms):
    """The reading generate_pages.py falls back to. Kept byte-identical in
    behaviour to the generator so the two never disagree about a count."""
    value = (value or "").strip()
    if not value:
        return None
    slug = periods_by_title.get(value)
    if slug:
        return slug
    low = value.lower()
    for term, term_slug in match_terms:
        if term.lower() in low:
            return term_slug
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridged", action="store_true",
                    help="list entries placed by the free-text bridge, not by period_slug")
    ap.add_argument("--list", metavar="SLUG",
                    help="list the entries on one period page")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any entry carries a slug not in periods.json")
    args = ap.parse_args()

    periods = load("periods.json")["periods"]
    legends = load("legends.json")["legends"]
    valid = [p["slug"] for p in periods]
    titles = {p["slug"]: p["title"] for p in periods}
    periods_by_title = {p["match"]: p["slug"] for p in periods}
    match_terms = sorted(periods_by_title.items(), key=lambda kv: -len(kv[0]))

    controlled = {s: [] for s in valid}
    bridged = {s: [] for s in valid}
    invalid = []
    unplaced = []

    for leg in legends:
        slug = (leg.get("period_slug") or "").strip() or None
        if slug and slug not in controlled:
            invalid.append((leg["name"], slug))
            slug = None
        if slug:
            controlled[slug].append(leg["name"])
            continue
        b = bridge_slug(leg.get("period"), periods_by_title, match_terms)
        if b:
            bridged[b].append(leg["name"])
        else:
            unplaced.append(leg["name"])

    if args.list:
        if args.list not in controlled:
            print("unknown period: %s" % args.list)
            print("expected one of: %s" % ", ".join(valid))
            return 2
        print("%s (%s)" % (titles[args.list], args.list))
        for n in sorted(controlled[args.list]):
            print("  slug    %s" % n)
        for n in sorted(bridged[args.list]):
            print("  bridge  %s" % n)
        return 0

    if args.bridged:
        print("Entries placed by the free-text `period` bridge, not by period_slug.")
        print("Each one is a candidate for the enrichment pass to read and decide.\n")
        for s in valid:
            for n in sorted(bridged[s]):
                print("  %-24s %s" % (s, n))
        print("\n%d entries." % sum(len(v) for v in bridged.values()))
        return 0

    n_ctl = sum(len(v) for v in controlled.values())
    n_brg = sum(len(v) for v in bridged.values())
    print("legends.json: %d entries, %d periods\n" % (len(legends), len(periods)))
    print("  %-26s %6s %7s %6s" % ("period", "slug", "bridge", "total"))
    print("  %-26s %6s %7s %6s" % ("-" * 26, "-" * 6, "-" * 7, "-" * 6))
    for s in valid:
        c, b = len(controlled[s]), len(bridged[s])
        flag = "  <-- empty" if c + b == 0 else ""
        print("  %-26s %6d %7d %6d%s" % (s, c, b, c + b, flag))
    print("  %-26s %6s %7s %6s" % ("-" * 26, "-" * 6, "-" * 7, "-" * 6))
    print("  %-26s %6d %7d %6d" % ("TOTAL", n_ctl, n_brg, n_ctl + n_brg))
    print("\n  %d entries on no period page." % len(unplaced))
    print("  That is not automatically wrong. Undatable oral tradition belongs")
    print("  on no period page, and `earliest_record` still dates its first")
    print("  appearance in print for the reader.")

    if invalid:
        print("\n  %d entries carry a slug that is not in periods.json:" % len(invalid))
        for name, slug in invalid[:20]:
            print("    %s = %s" % (name, slug))
        if args.strict:
            return 1
    elif args.strict:
        print("\n  OK: every period_slug is one of the %d canonical slugs." % len(valid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
