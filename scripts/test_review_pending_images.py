#!/usr/bin/env python3
"""End-to-end tests for review_pending_images.py, the image approval gate.

Why this exists: that script is the only thing in the pipeline allowed to write
into legend_pages.json and legend-images/, and on 2026-09-04 it was rewritten to
demand real copy from the candidate record instead of inventing NEEDS REVIEW
placeholders. The two refusal paths were checked by hand at the time. The path
that actually runs on a normal day, an approval that succeeds, was not, because
every candidate in the live manifest was already approved and faking one against
the real files was not worth the risk. This closes that gap.

Each case runs the real script, unmodified, in a throwaway directory holding a
miniature repo. generate_pages.py is stubbed: this is a test of the approval
gate, not of the generator, and the real one needs the whole dataset to run.

    python scripts/test_review_pending_images.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "review_pending_images.py")

LEGEND = "Test Legend of Somewhere"
SLUG = "test-legend-of-somewhere"

COPY = {
    "section_heading": "The stone by the water",
    "pullquote": "A single sentence taken from the entry's own text.",
    "alt_draft": "A weathered stone standing in long grass beside a grey estuary",
}

# The stub stands in for generate_pages.py. The approval refuses to report
# success unless the build produced both of these, so it has to make them.
STUB = """import io, json, os
os.makedirs('legend-images', exist_ok=True)
slugs = []
for f in os.listdir('legend-images'):
    if f.endswith('-hero.jpg'):
        s = f[:-len('-hero.jpg')]
        slugs.append(s)
        io.open(os.path.join('legend-images', s + '-hero.webp'), 'w').write('stub')
io.open(os.path.join('legend-images', 'manifest.json'), 'w').write(json.dumps(slugs))
print('stub generate_pages.py: %d image(s)' % len(slugs))
"""

failures = []


def build(tmp, candidate, pages=None):
    """A miniature repo: one legend, one staged candidate, a stub generator."""
    os.makedirs(os.path.join(tmp, "source_snapshots", "pending_images"))
    os.makedirs(os.path.join(tmp, "legend-images"))
    shutil.copy(SCRIPT, os.path.join(tmp, "review_pending_images.py"))
    io.open(os.path.join(tmp, "generate_pages.py"), "w", encoding="utf-8").write(STUB)

    write(tmp, "legends.json", {"legends": [{
        "name": LEGEND, "region": "Somewhere, Testshire", "category": "location",
        "period": "Attested in the test suite.",
    }]})
    write(tmp, "legend_pages.json", {"pages": pages or {}})
    write(tmp, os.path.join("source_snapshots", "pending_images", "manifest.json"),
          {"candidates": [candidate]})
    staged = os.path.join(tmp, "source_snapshots", "pending_images", SLUG + "-hero.jpg")
    io.open(staged, "w").write("not really a jpeg, nothing here decodes it")


def write(tmp, rel, obj):
    with io.open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def read(tmp, rel):
    with io.open(os.path.join(tmp, rel), encoding="utf-8") as f:
        return json.load(f)


def run(tmp, *args):
    p = subprocess.run([sys.executable, "review_pending_images.py"] + list(args),
                       cwd=tmp, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def candidate(**over):
    c = {"name": LEGEND, "slug": SLUG,
         "staged_path": "source_snapshots/pending_images/%s-hero.jpg" % SLUG,
         "prompt": "a test prompt", "generated_at": "2026-09-04T21:00:00Z",
         "status": "pending_review"}
    c.update(over)
    return c


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + ("" if cond else "  " + detail))
    if not cond:
        failures.append(label)


def case_missing_copy():
    print("\nA candidate with no copy is refused, and nothing is written")
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, candidate())
        code, out = run(tmp, "--approve", LEGEND)
        check("exits non-zero", code != 0, "code=%d" % code)
        check("names the missing fields",
              all(f in out for f in ("section_heading", "pullquote", "alt_draft")), out[:200])
        check("legend_pages.json untouched", read(tmp, "legend_pages.json")["pages"] == {})
        check("no image copied",
              not os.path.exists(os.path.join(tmp, "legend-images", SLUG + "-hero.jpg")))


def case_alt_unconfirmed():
    print("\nCopy present but alt not confirmed: shows the draft and stops")
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, candidate(**COPY))
        code, out = run(tmp, "--approve", LEGEND)
        check("exits non-zero", code != 0, "code=%d" % code)
        check("prints the alt draft", COPY["alt_draft"] in out, out[:200])
        check("offers --accept-alt", "--accept-alt" in out)
        check("legend_pages.json untouched", read(tmp, "legend_pages.json")["pages"] == {})


def case_accept():
    print("\n--accept-alt writes the staged copy and completes the build")
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, candidate(**COPY))
        code, out = run(tmp, "--approve", LEGEND, "--accept-alt")
        check("exits zero", code == 0, out[-400:])
        entry = read(tmp, "legend_pages.json")["pages"].get(LEGEND, {})
        check("entry created", bool(entry))
        check("alt is the staged draft", entry.get("alt") == COPY["alt_draft"], repr(entry.get("alt")))
        check("section_heading is the staged one",
              entry.get("section_heading") == COPY["section_heading"])
        check("pullquote is the staged one", entry.get("pullquote") == COPY["pullquote"])
        check("NO placeholder text anywhere in the entry",
              "NEEDS" not in json.dumps(entry), json.dumps(entry)[:200])
        check("image path points at the hero",
              entry.get("image") == "legend-images/%s-hero.jpg" % SLUG)
        check("facts built from the legend record",
              entry.get("facts", {}).get("Setting") == "Somewhere, Testshire")
        check("map_title set", entry.get("map_title") == "Somewhere, Testshire")
        check("image copied into place",
              os.path.exists(os.path.join(tmp, "legend-images", SLUG + "-hero.jpg")))
        man = read(tmp, os.path.join("source_snapshots", "pending_images", "manifest.json"))
        check("candidate marked approved", man["candidates"][0]["status"] == "approved")


def case_alt_override():
    print("\n--alt replaces the draft without needing --accept-alt")
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, candidate(**COPY))
        mine = "What I could actually see in the picture"
        code, out = run(tmp, "--approve", LEGEND, "--alt", mine)
        check("exits zero", code == 0, out[-400:])
        entry = read(tmp, "legend_pages.json")["pages"].get(LEGEND, {})
        check("alt is my wording, not the draft", entry.get("alt") == mine, repr(entry.get("alt")))


def case_duplicate():
    print("\nPreflight still refuses a legend that already has an entry")
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, candidate(**COPY), pages={LEGEND: {"image": "x", "alt": "already here"}})
        code, out = run(tmp, "--approve", LEGEND, "--accept-alt")
        check("exits non-zero", code != 0, "code=%d" % code)
        check("says why", "already has an entry" in out, out[:200])
        check("existing entry not overwritten",
              read(tmp, "legend_pages.json")["pages"][LEGEND]["alt"] == "already here")


def case_blank_copy():
    print("\nWhitespace-only copy counts as missing, not as copy")
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, candidate(section_heading="   ", pullquote="", alt_draft=COPY["alt_draft"]))
        code, out = run(tmp, "--approve", LEGEND, "--accept-alt")
        check("exits non-zero", code != 0, "code=%d" % code)
        check("legend_pages.json untouched", read(tmp, "legend_pages.json")["pages"] == {})


def main():
    print("review_pending_images.py, end to end")
    for case in (case_missing_copy, case_alt_unconfirmed, case_accept,
                 case_alt_override, case_duplicate, case_blank_copy):
        case()
    print()
    if failures:
        print("FAILED: %d check(s)" % len(failures), file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
