#!/usr/bin/env python3
"""Report scaffold placeholders that are one commit away from being published.

Why this exists: on 2026-09-04 the Tom Thumb page went live reading "NEEDS
EDITORIAL: a Heading for This Section", a placeholder pullquote, and a hero
image described as "NEEDS REVIEW: describe what the image actually shows for
Tom Thumb". It reached production inside a commit about My Archive bookmarking,
because nothing stood between the placeholder and the deploy except a reminder
printed by review_pending_images.py. A printed reminder is not a control.

Sixteen more were staged the same evening and caught by hand. This makes that
catch automatic.

    python scripts/placeholder_audit.py            # summary
    python scripts/placeholder_audit.py --list     # every offending value
    python scripts/placeholder_audit.py --strict   # exit 1 if any remain

Both sources are scanned, unlike dash_audit, and deliberately so. They fail
independently: legend_pages.json is the source, but a page built before the
copy was written keeps the placeholder in its markup until the next build, so
a clean JSON does not prove clean HTML.

A legend with NO legend_pages.json entry is NOT a failure. The generator
renders a category-coloured "Illustration in preparation" placeholder for those
(see generate_pages.py, the hero_placeholder branch), which is a finished state:
the legend is live and reads correctly, it is just waiting on artwork.
"""

import argparse
import glob
import io
import json
import os
import re
import sys

MARKERS = ("NEEDS REVIEW", "NEEDS EDITORIAL")
LEGEND_PAGES = "legend_pages.json"
PAGE_GLOB = os.path.join("legends", "**", "*.html")

# The fields review_pending_images.py scaffolds. Named explicitly so a new
# placeholder in some other field is reported as an unexpected one rather than
# quietly folded into the count.
SCAFFOLD_FIELDS = ("alt", "section_heading", "pullquote", "caption")


def entries(obj):
    """Yield (name, entry) for every legend_pages record, at any nesting."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, dict) and "image" in value:
                yield key, value
            elif isinstance(value, dict):
                yield from entries(value)


def scan_json(path):
    if not os.path.exists(path):
        return [], []
    data = json.loads(io.open(path, encoding="utf-8").read())
    hits, odd = [], []
    for name, entry in entries(data):
        for field, value in entry.items():
            if not isinstance(value, str):
                continue
            if any(m in value for m in MARKERS):
                (hits if field in SCAFFOLD_FIELDS else odd).append((name, field, value))
    return hits, odd


def scan_pages():
    hits = []
    for path in glob.glob(PAGE_GLOB, recursive=True):
        text = io.open(path, encoding="utf-8").read()
        found = set()
        for marker in MARKERS:
            for m in re.finditer(re.escape(marker) + r"[^\"<]{0,70}", text):
                found.add(" ".join(m.group(0).split()))
        if found:
            hits.append((path, sorted(found)))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print every offending value")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any remain")
    args = ap.parse_args()

    json_hits, odd = scan_json(LEGEND_PAGES)
    page_hits = scan_pages()

    by_entry = sorted({name for name, _, _ in json_hits})
    print(f"{LEGEND_PAGES}: {len(json_hits)} placeholder value(s) "
          f"across {len(by_entry)} entr{'y' if len(by_entry) == 1 else 'ies'}")
    print(f"built pages:       {len(page_hits)} page(s) carrying placeholder text")

    if odd:
        print(f"\n  {len(odd)} placeholder(s) in fields the scaffold does not write:")
        for name, field, value in odd:
            print(f"    [{name}] {field}: {value[:70]}")

    if args.list:
        if by_entry:
            print(f"\n=== {LEGEND_PAGES} ===")
            for name in by_entry:
                fields = [f for n, f, _ in json_hits if n == name]
                print(f"  {name}: {', '.join(sorted(fields))}")
        if page_hits:
            print("\n=== built pages ===")
            for path, found in page_hits:
                print(f"  {path}")
                for f in found:
                    print(f"      {f}")

    total = len(json_hits) + len(page_hits)
    if args.strict and total:
        print()
        print(f"FAIL: {len(json_hits)} placeholder value(s) in {LEGEND_PAGES} and "
              f"{len(page_hits)} built page(s) still carry scaffold text.",
              file=sys.stderr)
        print("Write the real copy before committing. A legend with no entry at "
              "all is fine; a half-written one is not.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
