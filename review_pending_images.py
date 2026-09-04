#!/usr/bin/env python3
"""Review and wire in Codex-generated hero image candidates.

Part of the automated hero-image pipeline: qc-merge's Step 8b generates
candidates and stages them under source_snapshots/pending_images/, but never
touches legend_pages.json or legend-images/ itself. This script is the human
visual-QA gate that PHOTOGRAPHY_STANDARDS.md requires before an image goes
live, and it is the only thing in the pipeline allowed to cross that boundary.

Usage:
    python review_pending_images.py                        list pending candidates
    python review_pending_images.py --approve "Legend Name"
    python review_pending_images.py --approve "Legend Name" --accept-alt
    python review_pending_images.py --approve "Legend Name" --alt "what you can see"
    python review_pending_images.py --reject "Legend Name" --reason "..."

Approving prints the alt text qc-merge staged and then stops, because alt has to
describe what the image ACTUALLY shows rather than what the prompt asked for.
Re-run with --accept-alt once you have looked, or --alt to write your own.

Run this only when you are actually going to look at the image. It is not
scheduled and should not be automated.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

REPO = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO)

MANIFEST_PATH = os.path.join("source_snapshots", "pending_images", "manifest.json")
PENDING_DIR = os.path.join("source_snapshots", "pending_images")
LEGEND_IMAGES_DIR = "legend-images"
LEGEND_PAGES_PATH = "legend_pages.json"
LEGENDS_PATH = "legends.json"
IMAGE_MANIFEST_PATH = os.path.join("legend-images", "manifest.json")


def slugify(name: str) -> str:
    """Must match generate_pages.py's slugify() exactly."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "legend"


def load_json(path):
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def load_manifest():
    m = load_json(MANIFEST_PATH)
    if m is None:
        return {"candidates": []}
    return m


def save_manifest(m):
    os.makedirs(PENDING_DIR, exist_ok=True)
    with io.open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)


def find_candidate(manifest, name):
    matches = [c for c in manifest["candidates"] if c["name"] == name]
    if not matches:
        return None
    # most recent first if there are somehow duplicates
    return sorted(matches, key=lambda c: c.get("generated_at", ""))[-1]


def cmd_list(manifest):
    pending = [c for c in manifest["candidates"] if c.get("status") == "pending_review"]
    if not pending:
        print("Nothing pending review.")
        return
    print(f"{len(pending)} candidate(s) pending review:\n")
    for c in pending:
        print(f"  {c['name']}")
        print(f"    staged:  {c['staged_path']}")
        print(f"    slug:    {c['slug']}")
        print(f"    prompt:  {c['prompt'][:120]}{'...' if len(c['prompt']) > 120 else ''}")
        print(f"    generated_at: {c.get('generated_at', '?')}")
        print()
    print("Open the staged files above to inspect them, then:")
    print('  python review_pending_images.py --approve "Legend Name"')
    print('  python review_pending_images.py --reject "Legend Name" --reason "..."')


def preflight(name, slug, legend_pages, legends_by_name):
    """The same three-source-of-truth check PHOTOGRAPHY_STANDARDS.md requires,
    re-run here in case anything changed since the candidate was staged."""
    problems = []
    if name not in legends_by_name:
        problems.append(f"'{name}' is not in legends.json at all")
    if legend_pages is not None and name in legend_pages.get("pages", {}):
        problems.append(f"legend_pages.json already has an entry for '{name}'")
    live_path = os.path.join(LEGEND_IMAGES_DIR, f"{slug}-hero.jpg")
    if os.path.exists(live_path):
        problems.append(f"{live_path} already exists")
    return problems


def build_facts(entry):
    facts = {}
    if entry.get("period"):
        facts["Tradition"] = entry["period"]
    cat = entry.get("category")
    if cat:
        facts["Type"] = cat.capitalize()
    if entry.get("region"):
        facts["Setting"] = entry["region"]
    return facts


def cmd_approve(manifest, name, accept_alt=False, alt_override=None):
    c = find_candidate(manifest, name)
    if c is None:
        sys.exit(f"No pending candidate found for '{name}'. Run with no arguments to list them.")
    if c.get("status") != "pending_review":
        sys.exit(f"'{name}' is already '{c.get('status')}', not pending_review.")

    slug = c["slug"]
    staged_path = c["staged_path"]
    if not os.path.exists(staged_path):
        sys.exit(f"Staged file missing on disk: {staged_path}")

    legends = load_json(LEGENDS_PATH) or {"legends": []}
    legends_by_name = {l["name"]: l for l in legends.get("legends", [])}
    legend_pages = load_json(LEGEND_PAGES_PATH) or {"pages": {}}

    problems = preflight(name, slug, legend_pages, legends_by_name)
    if problems:
        print("Preflight failed, refusing to wire this in:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    entry = legends_by_name[name]

    # The copy has to exist before anything is written. section_heading and
    # pullquote come from the entry's prose and never needed the image at all;
    # alt is the only one that depends on the picture, so it is the only one
    # you are asked to confirm.
    missing = [f for f in ("section_heading", "pullquote", "alt_draft")
               if not str(c.get(f, "")).strip()]
    if missing:
        sys.exit(
            f"Candidate for '{name}' has no {', '.join(missing)}.\n"
            "qc-merge Step 8b should stage these alongside the image. Refusing to\n"
            "wire in a half-written entry: that is what scripts/placeholder_audit.py\n"
            "now fails on. Add the copy to the candidate record and re-run."
        )

    # alt must describe what the image ACTUALLY shows, which is not always what
    # the prompt asked for. Tom Thumb's prompt described the tradition's small
    # stone; the illustration rendered an ordinary ledger slab. So the staged
    # alt is a draft, and approving it means you looked at the picture.
    alt = (alt_override or "").strip() or c["alt_draft"].strip()
    if not alt_override:
        print(f"\nStaged alt draft:\n  {alt}")
        if not accept_alt:
            sys.exit(
                "\nLook at the image, then re-run with --accept-alt if that describes\n"
                'it, or --alt "..." to replace it.'
            )

    # 1. copy the staged image into place first, so the manifest glob in
    #    generate_pages.py picks it up in the same run as the metadata below.
    live_path = os.path.join(LEGEND_IMAGES_DIR, f"{slug}-hero.jpg")
    shutil.copyfile(staged_path, live_path)
    print(f"copied {staged_path} -> {live_path}")

    # 2. write the legend_pages.json entry, using the copy qc-merge Step 8b
    #    staged alongside the image. This used to write NEEDS REVIEW /
    #    NEEDS EDITORIAL placeholders and print a reminder, which is exactly
    #    how Tom Thumb reached production inside an unrelated commit.
    pages = legend_pages.setdefault("pages", {})
    max_priority = max((v.get("priority", 0) for v in pages.values()), default=0)
    pages[name] = {
        "priority": max_priority + 1,
        "image": f"legend-images/{slug}-hero.jpg",
        "alt": alt,
        "caption": (c.get("caption") or "").strip() or f"A visual interpretation of {name}",
        "map_title": entry.get("region", ""),
        "section_heading": c["section_heading"].strip(),
        "pullquote": c["pullquote"].strip(),
        "editorial": "",
        "editorial_by": "",
        "facts": build_facts(entry),
        "seo_title": f"{name} · Folklore Finder",
    }
    with io.open(LEGEND_PAGES_PATH, "w", encoding="utf-8") as f:
        json.dump(legend_pages, f, indent=2, ensure_ascii=False)
    print(f"wrote legend_pages.json entry for '{name}' (placeholders marked NEEDS REVIEW/NEEDS EDITORIAL)")

    # 3. update the pending-images manifest before the build, so a crash here
    #    doesn't leave the candidate looking untouched.
    c["status"] = "approved"
    save_manifest(manifest)

    # 4. build.
    print("running generate_pages.py ...")
    result = subprocess.run([sys.executable, "generate_pages.py"], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit("generate_pages.py failed. legend_pages.json and the copied image are in place; "
                 "fix the build error and re-run generate_pages.py by hand, then commit.")

    # 5. validate.
    image_manifest = load_json(IMAGE_MANIFEST_PATH) or []
    if slug not in image_manifest:
        sys.exit(f"'{slug}' did not appear in legend-images/manifest.json after the build. "
                  "Something is wrong; do not commit.")
    webp_path = os.path.join(LEGEND_IMAGES_DIR, f"{slug}-hero.webp")
    if not os.path.exists(webp_path):
        sys.exit(f"generate_pages.py did not derive {webp_path}. Something is wrong; do not commit.")

    print(f"\n'{name}' is wired in and built, with its copy in place.")
    print("Run `python scripts/placeholder_audit.py --strict` before committing.")
    print("\nNext: review the placeholders, then commit and push, e.g.:")
    print(f'  git add legend-images/{slug}-hero.jpg legend-images/{slug}-hero.webp '
          f'legend-images/{slug}-hero-card.webp legend-images/manifest.json legend_pages.json '
          f'legends/{slug}.html sitemap.xml feed.xml')
    print(f'  git commit -m "Hero image: {name} (reviewed)"')
    print('  git push')


def cmd_reject(manifest, name, reason):
    c = find_candidate(manifest, name)
    if c is None:
        sys.exit(f"No pending candidate found for '{name}'.")
    c["status"] = "rejected"
    c["rejected_reason"] = reason or ""
    save_manifest(manifest)
    print(f"'{name}' marked rejected. Staged file left in place at {c['staged_path']} for reference.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--approve", metavar="NAME", help="Wire this candidate's image in and build")
    ap.add_argument("--reject", metavar="NAME", help="Mark this candidate rejected")
    ap.add_argument("--reason", default="", help="Reason for --reject")
    ap.add_argument("--accept-alt", action="store_true",
                    help="Confirm the staged alt draft describes the image you just looked at")
    ap.add_argument("--alt", metavar="TEXT", default=None,
                    help="Replace the staged alt draft with your own wording")
    args = ap.parse_args()

    manifest = load_manifest()

    if args.approve:
        cmd_approve(manifest, args.approve, accept_alt=args.accept_alt, alt_override=args.alt)
    elif args.reject:
        cmd_reject(manifest, args.reject, args.reason)
    else:
        cmd_list(manifest)


if __name__ == "__main__":
    main()
