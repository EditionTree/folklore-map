#!/usr/bin/env python3
"""Build the home-screen icon set from green-man.png.

The emblem is the only brand mark the site has at icon scale: a flat
single-colour gold line drawing, 256x256 RGBA, whose art occupies 218x229 of
that canvas. Everything here is sized off the ART, not the canvas, so the
padding in the source file does not silently eat into the icon.

256px is the largest master that exists, so the 512 "any" icon involves a ~1.5x
upscale. That is the one soft output and it is deliberate: flat line art
tolerates LANCZOS far better than photography, and the alternative -- shipping
no 512 -- means Android falls back to a generated icon instead. The maskable
variant needs no upscale at all, because a maskable icon wants the mark small.

MASKABLE_FRAC is the number that matters. A maskable icon is cropped by the
platform to an arbitrary shape inside a circle 80% of the icon's width, so any
mark outside that circle can be sliced off. 0.46 leaves the emblem comfortably
inside it on every mask shape Android ships.

Apple's icon is flattened onto the brand brown on purpose: iOS composites alpha
against black, so a transparent PNG here renders as a black tile.

Run: python scripts/build_app_icons.py [--check]
"""
import argparse
import os

from PIL import Image

SOURCE = "green-man.png"
OUT_DIR = "assets/icons"

# --ff-bar-brown, the nav and footer bar. Fixed by Canonical Site Chrome, and
# the same value the theme-color meta and the manifest carry.
BRAND_BROWN = (26, 14, 6)

ANY_FRAC = 0.62       # ordinary icon: mark fills most of the tile
MASKABLE_FRAC = 0.46  # inside the 80%-width safe circle, with room to spare

# (filename, canvas px, art fraction)
ICONS = [
    ("icon-192.png", 192, ANY_FRAC),
    ("icon-512.png", 512, ANY_FRAC),
    ("icon-maskable-512.png", 512, MASKABLE_FRAC),
    # Not in the manifest -- iOS reads it from a <link> instead, and wants 180.
    ("apple-touch-icon.png", 180, ANY_FRAC),
]


def emblem():
    """The source art, cropped to its own ink so padding is ours to choose."""
    im = Image.open(SOURCE).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def render(art, size, frac):
    canvas = Image.new("RGBA", (size, size), BRAND_BROWN + (255,))
    # Fit the longer edge, so a non-square mark keeps its proportions.
    scale = (size * frac) / max(art.size)
    w, h = (max(1, round(d * scale)) for d in art.size)
    resized = art.resize((w, h), Image.LANCZOS)
    canvas.alpha_composite(resized, ((size - w) // 2, (size - h) // 2))
    # Flatten: every consumer here wants an opaque tile, and iOS *needs* one.
    return canvas.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing")
    args = ap.parse_args()

    art = emblem()
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"{SOURCE}: art {art.size[0]}x{art.size[1]} after crop")

    for name, size, frac in ICONS:
        path = os.path.join(OUT_DIR, name)
        img = render(art, size, frac)
        mark = round(size * frac)
        upscale = mark / max(art.size)
        note = f"  mark {mark}px ({upscale:.2f}x source)"
        if args.check:
            state = "exists" if os.path.exists(path) else "MISSING"
            print(f"  {name:<26} {size}x{size}  {state}{note}")
            continue
        img.save(path, "PNG", optimize=True)
        kb = os.path.getsize(path) / 1024
        print(f"  {name:<26} {size}x{size}  {kb:5.1f} KB{note}")


if __name__ == "__main__":
    main()
