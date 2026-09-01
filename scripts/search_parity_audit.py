# -*- coding: utf-8 -*-
"""Fail if search scoring or category labels drift out of their single source.

Why this exists
---------------
Twice now the same thing has happened. In August the category label map was
duplicated across js/map.js and js/home.js and drifted on `pirate`; the fix
created js/categories.js but missed two further copies, in nav-search.js and
build_legends.py, so the site shipped "Pirates" from one file and
"Pirates & Smugglers" from another for nine days.

Then on 2026-09-01 the same pattern surfaced in the search scorer. Three copies
of scoreLegend existed. Only the map's ever learned about period_slug, so
searching "stuart" returned 50 legends on the map and zero in the nav search
box that ships on 829 pages.

Both are the same failure: logic copied rather than shared, then edited in one
place. This checks the two rules that keep them honest.

    python scripts/search_parity_audit.py            report
    python scripts/search_parity_audit.py --strict   exit 1 on drift
"""
from __future__ import print_function
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON_JS = os.path.join(REPO, "js", "categories.js")
SCORER = os.path.join(REPO, "js", "search-score.js")


def read(p):
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def js_files():
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in
                   (".git", "node_modules", "source_snapshots", "_drafts",
                    "assets", "_fieldguide_build", ".claude", "__pycache__")]
        for f in files:
            if f.endswith(".js"):
                out.append(os.path.join(root, f))
    return sorted(out)


def canonical_labels():
    """The labels in js/categories.js, which is the single source of truth."""
    return dict(re.findall(r'(\w+):\s*\{\s*label:\s*"([^"]+)"', read(CANON_JS)))


def main():
    strict = "--strict" in sys.argv
    fails = []
    canon = canonical_labels()
    if not canon:
        print("could not parse js/categories.js")
        return 1
    print("canonical labels in js/categories.js: %d" % len(canon))

    # ---- Rule 1: only js/search-score.js may implement the scoring ladder.
    # A consumer may still define scoreLegend as a thin wrapper, but it must
    # delegate. The tell for a real implementation is the ladder's own score
    # constants appearing outside the scorer.
    print("\nRule 1: one implementation of the scoring ladder")
    LADDER = re.compile(r"(?:return|score\s*=)\s*(?:100|95|90|80|75|65|60|55|45|40|25|20|35|30|15)\b")
    for p in js_files():
        rel = os.path.relpath(p, REPO).replace("\\", "/")
        if rel == "js/search-score.js":
            continue
        src = read(p)
        if "scoreLegend" not in src and "FF_SEARCH" not in src:
            continue
        hits = len(LADDER.findall(src))
        delegates = "FF_SEARCH" in src
        # nav-search.js keeps a deliberate reduced fallback for the case where
        # Rocket Loader reorders the two scripts. Five constants is that
        # fallback; more than that means a ladder has grown back.
        limit = 5 if rel == "nav-search.js" else 0
        status = "ok"
        if not delegates:
            status = "*** does not delegate to FF_SEARCH ***"
            fails.append(rel + ": no delegation")
        elif hits > limit:
            status = "*** %d score constants (limit %d) ***" % (hits, limit)
            fails.append(rel + ": ladder reappeared")
        print("  %-24s delegates=%-5s constants=%-3d %s" % (rel, delegates, hits, status))

    # ---- Rule 2: every category label map agrees with js/categories.js.
    print("\nRule 2: category labels agree everywhere")
    sources = [
        ("js/search-score.js", re.compile(r'(\w+):\s*"([^"]+)"')),
        ("nav-search.js", re.compile(r'(\w+):\s*"([^"]+)"')),
        ("build_legends.py", re.compile(r'"(\w+)":\s*"([^"]+)"')),
    ]
    for rel, pat in sources:
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        src = read(p)
        found = {k: v for k, v in pat.findall(src) if k in canon}
        if not found:
            print("  %-24s no label map (uses the shared one)" % rel)
            continue
        bad = {k: (v, canon[k]) for k, v in found.items() if v != canon[k]}
        print("  %-24s %d labels, %d disagree" % (rel, len(found), len(bad)))
        for k, (got, want) in sorted(bad.items()):
            print("      %-10s has %-24s canonical is %s" % (k, '"%s"' % got, '"%s"' % want))
            fails.append("%s: %s label" % (rel, k))

    print("\n" + ("DRIFT: " + "; ".join(fails) if fails else "No drift. One scorer, one label map."))
    return 1 if (strict and fails) else 0


if __name__ == "__main__":
    sys.exit(main())
