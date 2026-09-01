# -*- coding: utf-8 -*-
"""Check every constrained field against the values Supabase will actually accept.

Why this exists
---------------
On 2026-09-01 nine new entries were written with invented `origin_type` values
("urban-legend", "antiquarian", "documented", "local-tradition"). Nothing local
objected. The whole 719-row sync was rejected by Postgres with a 23514 check
violation, and the failure surfaced as a truncated row dump that named only the
first offending entry, so the real scope was invisible from the error alone.

The values below mirror the CHECK constraints on public.legends. Keep them in
step with the migrations. If a migration widens a constraint, widen this list in
the same commit, the way period_slug was added to rls_regression_test.py's
expected column set.

    python scripts/enum_audit.py            report
    python scripts/enum_audit.py --strict   exit 1 if anything is invalid

Checks legends.json AND seeds.json, because seeds is the source of truth and a
fix applied only to legends.json is reverted by the next pipeline run.
"""
from __future__ import print_function
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mirrors legends_origin_type_check, legends_dating_confidence_check and
# legends_period_slug_check. NULL is permitted by all three.
ALLOWED = {
    "origin_type": {
        "oral-tradition", "literary", "archaeological", "historical-event",
    },
    "dating_confidence": {
        "high", "medium", "low",
    },
    "period_slug": {
        "prehistoric-britain", "bronze-age", "iron-age", "roman-britain",
        "sub-roman-britain", "early-medieval-britain", "viking-age",
        "norman-britain", "medieval-britain", "tudor-britain",
        "stuart-britain", "georgian-britain", "victorian-britain",
        "edwardian-britain", "modern-folklore",
    },
}


def load(path):
    with io.open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if isinstance(doc, dict) and "legends" in doc:
        return doc["legends"]
    return doc


def audit(entries, label):
    bad = []
    for e in entries:
        for field, allowed in sorted(ALLOWED.items()):
            v = e.get(field)
            if v is None or v == "":
                continue
            if v not in allowed:
                bad.append((e.get("name", "?"), field, v))
    print("%s: %d entries" % (label, len(entries)))
    for field in sorted(ALLOWED):
        used = sorted({e.get(field) for e in entries if e.get(field)})
        unknown = [u for u in used if u not in ALLOWED[field]]
        print("  %-18s %2d value(s) in use%s"
              % (field, len(used), ", %d INVALID" % len(unknown) if unknown else ""))
    if bad:
        print("  INVALID:")
        for name, field, v in bad:
            print("    %-38s %-18s %r" % (name, field, v))
    return bad


def main():
    strict = "--strict" in sys.argv
    total = []
    for fname, label in (("legends.json", "legends.json"), ("seeds.json", "seeds.json")):
        path = os.path.join(REPO, fname)
        if not os.path.exists(path):
            print("%s: not found, skipped" % fname)
            continue
        total += audit(load(path), label)
        print("")

    if total:
        print("%d invalid value(s). Supabase will reject the sync with a 23514."
              % len(total))
        print("Fix seeds.json first, then rebuild, or the next pipeline run undoes it.")
    else:
        print("All constrained fields hold values Supabase will accept.")
    return 1 if (strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
