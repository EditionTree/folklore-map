#!/usr/bin/env python3
"""Audit folklore-map coordinates with OpenStreetMap reverse geocoding."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "FolkloreMap-CoordinateAudit/1.0 (manual data quality review)"
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
WATER_TYPES = {
    "bay", "basin", "canal", "harbour", "lake", "loch", "ocean", "reservoir",
    "river", "sea", "strait", "stream", "water", "waterway",
}


def reverse_geocode(lat, lng):
    params = urlencode({
        "format": "jsonv2",
        "lat": lat,
        "lon": lng,
        "zoom": 18,
        "addressdetails": 1,
    })
    request = Request(f"{REVERSE_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def classify(result):
    category = str(result.get("category", "")).lower()
    place_type = str(result.get("type", "")).lower()
    address = result.get("address", {})
    address_keys = {str(key).lower() for key in address}
    if not result.get("place_id"):
        return "unresolved"
    if category in {"natural", "waterway"} and place_type in WATER_TYPES:
        return "water"
    if place_type in WATER_TYPES or address_keys.intersection(WATER_TYPES):
        return "water"
    return "land_or_named_feature"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="legends.json")
    parser.add_argument("--output", default="source_snapshots/coordinate_audit.json")
    parser.add_argument("--delay", type=float, default=1.05)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--name")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    legends = json.loads(Path(args.input).read_text(encoding="utf-8"))["legends"]
    if args.name:
        legends = [legend for legend in legends if legend["name"] == args.name]
    if args.limit:
        legends = legends[:args.limit]

    sys.stdout.reconfigure(errors="replace")
    path = Path(args.output)
    rows = []
    if args.resume and path.exists():
        rows = json.loads(path.read_text(encoding="utf-8")).get("results", [])
    completed_names = {row["name"] for row in rows}

    for index, legend in enumerate(legends, 1):
        if legend["name"] in completed_names:
            continue
        try:
            result = reverse_geocode(legend["lat"], legend["lng"])
            status = classify(result)
            error = ""
        except (HTTPError, URLError, TimeoutError) as exc:
            result = {}
            status = "error"
            error = str(exc)
        rows.append({
            "name": legend["name"],
            "lat": legend["lat"],
            "lng": legend["lng"],
            "category": legend["category"],
            "region": legend["region"],
            "status": status,
            "osm_category": result.get("category", ""),
            "osm_type": result.get("type", ""),
            "display_name": result.get("display_name", ""),
            "error": error,
        })
        print(f"[{index}/{len(legends)}] {legend['name']}: {status}")
        write_output(path, args.input, rows)
        if index < len(legends):
            time.sleep(args.delay)

    write_output(path, args.input, rows)
    print(f"Wrote {path}")


def write_output(path, input_path, rows):
    output = {
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input": input_path,
        "total": len(rows),
        "water_or_unresolved": [
            row for row in rows if row["status"] in {"water", "unresolved", "error"}
        ],
        "results": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
