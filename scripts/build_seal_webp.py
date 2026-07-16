#!/usr/bin/env python3
"""Convert the achievement wax seals to display-sized WebP.

The masters in assets/achievements/wax-seals-v2/ are 627x627 RGBA PNGs (~418KB
each), but a seal never renders larger than 132px (104px desktop grid, 116px
mobile, 132px unlock popup, 56px in My Archive). TARGET_PX keeps a 2.4x margin
over that for high-DPI screens.

Seals render as <img>, so the WebP border-image gotcha (see the oak-branch
frame) does not apply here. Alpha is preserved -- the hue-rotate/saturate
tinting in achievements.html relies on it.

Run: python scripts/build_seal_webp.py [--check]
"""
import argparse
import glob
import io
import math
import os

from PIL import Image, ImageChops

SEAL_DIR = "assets/achievements/wax-seals-v2"
TARGET_PX = 320
QUALITY = 90
# Card background the seals sit on -- only used for the quality check, so that
# undefined RGB in fully-transparent pixels doesn't pollute the measurement.
PARCHMENT = (240, 233, 214, 255)
DISPLAY_PX = 132


def encode(im):
    buf = io.BytesIO()
    im.convert("RGBA").resize((TARGET_PX, TARGET_PX), Image.LANCZOS).save(
        buf, "WEBP", quality=QUALITY, method=6)
    return buf.getvalue()


def _composite(im, size):
    im = im.convert("RGBA").resize((size, size), Image.LANCZOS)
    bg = Image.new("RGBA", (size, size), PARCHMENT)
    return Image.alpha_composite(bg, im).convert("RGB")


def psnr_at_display(src_path, webp_bytes):
    """Difference between old and new AS RENDERED, composited on the card bg."""
    ref = _composite(Image.open(src_path), DISPLAY_PX)
    new = _composite(Image.open(io.BytesIO(webp_bytes)), DISPLAY_PX)
    px = list(ImageChops.difference(ref, new).getdata())
    mse = sum(sum(c * c for c in p) / 3 for p in px) / len(px)
    return 100.0 if mse == 0 else 10 * math.log10(255.0 ** 2 / mse)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report quality/size without writing files")
    args = ap.parse_args()

    srcs = sorted(glob.glob(os.path.join(SEAL_DIR, "*.png")))
    if not srcs:
        raise SystemExit(f"no PNG seals found in {SEAL_DIR}/")

    before = after = 0
    worst = (999.0, "")
    for src in srcs:
        data = encode(Image.open(src))
        before += os.path.getsize(src)
        after += len(data)

        p = psnr_at_display(src, data)
        if p < worst[0]:
            worst = (p, os.path.basename(src))

        if not args.check:
            with open(os.path.splitext(src)[0] + ".webp", "wb") as f:
                f.write(data)

    verb = "would write" if args.check else "wrote"
    print(f"{verb} {len(srcs)} seals @ {TARGET_PX}px q{QUALITY}")
    print(f"  {before/1048576:.1f}MB -> {after/1048576:.1f}MB "
          f"({100 - 100*after/before:.1f}% smaller, "
          f"{after/len(srcs)/1024:.0f}KB avg)")
    print(f"  worst PSNR at {DISPLAY_PX}px: {worst[0]:.1f}dB ({worst[1]})")


if __name__ == "__main__":
    main()
