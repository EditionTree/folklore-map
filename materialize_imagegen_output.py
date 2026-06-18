#!/usr/bin/env python3
"""Materialise built-in Codex image generation output from local session logs.

The built-in image tool can return an inline base64 raster with savedPath=null.
This helper turns that local session-log payload into a workspace image file so
project automations can continue without using the API fallback path.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass
class ImageCandidate:
    session: Path
    timestamp: datetime
    image_id: str
    prompt: str
    result: str


def parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def session_files(root: Path, since: datetime | None) -> list[Path]:
    sessions_root = root / "sessions"
    if not sessions_root.exists():
        return []
    files = [p for p in sessions_root.rglob("*.jsonl") if p.is_file()]
    if since is not None:
        files = [
            p
            for p in files
            if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) >= since
        ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def image_candidates(path: Path, prompt_contains: str) -> list[ImageCandidate]:
    candidates: list[ImageCandidate] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("type") not in {"response_item", "event_msg"}:
                continue
            payload = record.get("payload") or {}
            if payload.get("type") not in {
                "imageGeneration",
                "image_generation_call",
                "image_generation_end",
            }:
                continue

            result = payload.get("result")
            if not result:
                continue

            prompt = payload.get("revisedPrompt") or payload.get("revised_prompt") or ""
            if prompt_contains and prompt_contains.lower() not in prompt.lower():
                continue

            try:
                timestamp = parse_timestamp(record["timestamp"])
            except Exception:
                timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)

            candidates.append(
                ImageCandidate(
                    session=path,
                    timestamp=timestamp,
                    image_id=payload.get("id") or payload.get("call_id") or "",
                    prompt=prompt,
                    result=result,
                )
            )
    return candidates


def find_candidate(args: argparse.Namespace) -> ImageCandidate | None:
    since = None
    if args.since_minutes is not None:
        since = datetime.now(timezone.utc) - timedelta(minutes=args.since_minutes)

    paths = [args.session] if args.session else session_files(codex_home(), since)
    candidates: list[ImageCandidate] = []
    for path in paths:
        if path and path.exists():
            candidates.extend(image_candidates(path, args.prompt_contains or ""))

    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.timestamp, reverse=True)[0]


def save_candidate(candidate: ImageCandidate, out: Path, quality: int) -> None:
    image_bytes = base64.b64decode(candidate.result)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.suffix.lower() in {".jpg", ".jpeg"}:
        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    else:
        out.write_bytes(image_bytes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save the latest built-in image_gen result from local Codex session logs."
    )
    parser.add_argument("--out", type=Path, required=True, help="Output image path, usually legend-images/name-hero.jpg")
    parser.add_argument("--session", type=Path, help="Specific session JSONL file to scan")
    parser.add_argument("--prompt-contains", default="", help="Only use an image whose revised prompt contains this text")
    parser.add_argument("--since-minutes", type=int, default=120, help="Only scan recently modified session logs")
    parser.add_argument("--quality", type=int, default=82, help="JPEG quality when --out ends in .jpg or .jpeg")
    parser.add_argument("--print-source", action="store_true", help="Print the session and image id used")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate = find_candidate(args)
    if candidate is None:
        print("No imageGeneration result found in local Codex session logs.", file=sys.stderr)
        return 1

    save_candidate(candidate, args.out, args.quality)
    if args.print_source:
        print(f"saved {args.out}")
        print(f"session {candidate.session}")
        print(f"image {candidate.image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
