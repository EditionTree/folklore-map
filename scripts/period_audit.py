#!/usr/bin/env python3
"""Report Explore Through Time coverage from the controlled `period_slug` field.

Why this exists: `period` is 626 distinct free-text values across 710 entries,
and it mixes two different facts in one field. Some values say when the legend
is SET ("Restoration England, 17th century"), some say when it was RECORDED
("First published 1865"), and 289 say both in one sentence. A period page can
only mean one of those, and it means the first: see periods.json's `_comment`
and content-style-guide.md under "Assigning period_slug".

`period_slug` is the controlled answer, and since 2026-08-31 it is the ONLY
thing that puts a legend on a period page. All 710 entries have been reviewed
by hand: 479 carry a slug, 231 were reviewed and deliberately left without one.

The free-text bridge this script used to model was deleted from
generate_pages.py on 2026-08-31, and removed from here in the same change. An
audit that models behaviour the site no longer has is worse than no audit: it
was reporting 9 entries as placed that the site had already stopped placing.

    python scripts/period_audit.py              # coverage table
    python scripts/period_audit.py --list victorian-britain
    python scripts/period_audit.py --unplaced   # entries with no period
    python scripts/period_audit.py --strict     # exit 1 on an invalid slug

--strict fails ONLY on a slug that is not in periods.json. Thin or empty pages
are not failures: the fifteen periods are a fixed historical framework, and a
page fills when entries honestly belong on it. Nor is an entry without a slug a
failure. Undatable oral tradition (Black Shuck, the Banshee, the Brownie) is
correctly on no period page, and `earliest_record` still tells the reader when
it first appears in print.
"""

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    return json.load(io.open(os.path.join(ROOT, name), encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", metavar="SLUG", help="list the entries on one period page")
    ap.add_argument("--unplaced", action="store_true",
                    help="list the entries that carry no period_slug")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any entry carries a slug not in periods.json")
    args = ap.parse_args()

    periods = load("periods.json")["periods"]
    legends = load("legends.json")["legends"]
    valid = [p["slug"] for p in periods]
    titles = {p["slug"]: p["title"] for p in periods}

    members = {s: [] for s in valid}
    invalid, unplaced = [], []

    for leg in legends:
        slug = (leg.get("period_slug") or "").strip() or None
        if slug is None:
            unplaced.append(leg["name"])
        elif slug in members:
            members[slug].append(leg["name"])
        else:
            invalid.append((leg["name"], slug))

    if args.list:
        if args.list not in members:
            print("unknown period: %s" % args.list)
            print("expected one of: %s" % ", ".join(valid))
            return 2
        print("%s (%s), %d entries\n" % (titles[args.list], args.list,
                                         len(members[args.list])))
        for n in sorted(members[args.list]):
            print("  " + n)
        return 0

    if args.unplaced:
        print("Entries with no period_slug. Each has been reviewed; an absent")
        print("value is a decision, not a gap.\n")
        for n in sorted(unplaced):
            print("  " + n)
        print("\n%d entries." % len(unplaced))
        return 0

    placed = sum(len(v) for v in members.values())
    print("legends.json: %d entries, %d periods\n" % (len(legends), len(periods)))
    print("  %-26s %7s" % ("period", "entries"))
    print("  %-26s %7s" % ("-" * 26, "-" * 7))
    for s in valid:
        flag = "  <-- empty" if not members[s] else ""
        print("  %-26s %7d%s" % (s, len(members[s]), flag))
    print("  %-26s %7s" % ("-" * 26, "-" * 7))
    print("  %-26s %7d" % ("TOTAL", placed))
    print("\n  %d entries on no period page, all reviewed." % len(unplaced))
    print("  Undatable oral tradition belongs on no period page, and")
    print("  `earliest_record` still dates its first appearance in print.")

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
