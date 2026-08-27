#!/usr/bin/env python3
"""Report writing that talks about the pipeline instead of about the legend.

Why this exists: every field scanned here renders on a live legend page. The
`earliest_record` value sits under "Earliest Written Record" in the sidebar,
where a visitor reads it as a fact about the legend. Measured 2026-08-27, 130
entries were instead telling the visitor about the research process that
produced them, in phrases like "enriched in an earlier run today", "could not
be resolved within budget", and "per this entry's own detail text". None of
that means anything to a reader, and some of it reads as an unfinished draft.

This is the same shape of problem as the em-dash rule, and it rotted the same
way: a house style that nobody could check. So it is checkable.

    python scripts/voice_audit.py             # summary
    python scripts/voice_audit.py --list      # every offending value
    python scripts/voice_audit.py --tier leak --list
    python scripts/voice_audit.py --strict    # exit 1 if any LEAK remains

Two tiers, deliberately:

  LEAK  - the value refers to the pipeline, the page's own structure, or the
          research budget. Always wrong in visitor-facing copy, and always
          fixable by deleting the clause. --strict fails on these.
  VOICE - honest uncertainty phrased as a research log ("no version was
          located"). The FACT is right and must be kept; only the phrasing is
          off, so this is reported and never fails. Rewrite as a plain
          statement ("no earlier version has been found") when you are already
          editing the value. Do not delete the uncertainty itself: stating it
          is required by BRAND_GUIDE.md section 10.
"""

import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every field here renders on the legend page.
FIELDS = ["summary", "detail", "earliest_record", "period",
          "historical_setting", "cultural_tradition", "origin_date"]

LEAK = [
    ("pipeline run",
     re.compile(r"\b(?:in|from)\s+(?:an|the)\s+(?:earlier|previous|last)\s+run\b"
                r"|\bthis\s+run\b|\benriched\s+in\b"
                r"|\balready\s+(?:used|enriched)\s+for\b", re.I)),
    ("the page's own structure",
     re.compile(r"this\s+entry's\s+own\b|\balready\s+noted\s+in\s+this\s+entry\b"
                r"|\bper\s+this\s+entry\b|\bthe\s+existing\s+(?:summary|detail)\b"
                r"|\bthis\s+entry's\s+(?:summary|detail)\b", re.I)),
    ("research process or budget",
     re.compile(r"\bwithin\s+budget\b|\bflagged\s+for\s+editorial\b"
                r"|\bfor\s+editorial\s+attention\b|\bNotable\s+finding\b", re.I)),
]

# Narrowed 2026-08-27, after the LEAK cleanup cleared the budget talk. The
# original pattern also matched "could not be confirmed" and "has been traced
# earlier than", which only ever read badly in the company of "within budget".
# On their own they are ordinary honest prose, and flagging them would push an
# editor to reword sentences that are already fine. "Located" is the tell that
# survives: research vocabulary, never how anyone describes a legend.
VOICE = [
    ("research-log phrasing",
     re.compile(r"\b(?:was|were)\s+located\b|\bso\s+far\s+located\b"
                r"|\bcould\s+not\s+be\s+located\b", re.I)),
]


def scan(legends, rules):
    """-> [(name, field, label, excerpt)]"""
    hits = []
    for leg in legends:
        for f in FIELDS:
            v = leg.get(f)
            if not isinstance(v, str):
                continue
            for label, rx in rules:
                m = rx.search(v)
                if m:
                    a, b = max(0, m.start() - 60), min(len(v), m.end() + 50)
                    hits.append((leg.get("name", "?"), f, label,
                                 v[a:b].replace("\n", " ")))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print every offending value")
    ap.add_argument("--tier", choices=["leak", "voice"], help="restrict to one tier")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any LEAK remains")
    args = ap.parse_args()

    legends = json.load(io.open(os.path.join(ROOT, "legends.json"),
                                encoding="utf-8"))["legends"]
    tiers = []
    if args.tier != "voice":
        tiers.append(("LEAK", scan(legends, LEAK)))
    if args.tier != "leak":
        tiers.append(("VOICE", scan(legends, VOICE)))

    print("legends.json: %d entries, %d rendered fields scanned\n"
          % (len(legends), len(FIELDS)))

    leak_total = 0
    for tier, hits in tiers:
        names = {h[0] for h in hits}
        by_label = {}
        for _, _, label, _ in hits:
            by_label[label] = by_label.get(label, 0) + 1
        print("  %s: %d values across %d entries" % (tier, len(hits), len(names)))
        for label in sorted(by_label, key=lambda k: -by_label[k]):
            print("    %-30s %4d" % (label, by_label[label]))
        if tier == "LEAK":
            leak_total = len(hits)
        if args.list:
            print("")
            for name, field, label, excerpt in sorted(hits):
                print("    %s :: %s  [%s]" % (name, field, label))
                print("       ...%s..." % excerpt)
        print("")

    if args.strict:
        if leak_total:
            print("FAIL: %d values still talk about the pipeline." % leak_total,
                  file=sys.stderr)
            print("Delete the clause. It says nothing to a reader.", file=sys.stderr)
            return 1
        print("  OK: no pipeline talk in visitor-facing copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
