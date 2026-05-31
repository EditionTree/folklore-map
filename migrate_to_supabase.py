#!/usr/bin/env python3
"""
migrate_to_supabase.py — One-time migration from legends.json to Supabase

Run this ONCE after setting up your Supabase table.
After this, build_legends.py writes directly to Supabase.

Usage:
    python migrate_to_supabase.py

Requires:
    pip install requests

Credentials:
    Set SUPABASE_URL and SUPABASE_SERVICE_KEY below,
    or set them as environment variables.
"""

import json
import os
import sys
import time

import requests

# ── CREDENTIALS ─────────────────────────────────────────────────────────
# Get these from your Supabase project:
#   Settings → API → Project URL  (SUPABASE_URL)
#   Settings → API → service_role key  (SUPABASE_SERVICE_KEY)
#
# The service_role key bypasses Row Level Security — keep it private,
# never put it in index.html or commit it to a public GitHub repo.

SUPABASE_URL        = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "YOUR_SERVICE_KEY_HERE")

LEGENDS_FILE = "legends.json"
BATCH_SIZE   = 50    # Supabase handles up to 500 rows per request, 50 is safe
RATE_LIMIT   = 0.2   # seconds between batches


def get_headers():
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal,resolution=merge-duplicates",
    }


def check_credentials():
    if "YOUR_SUPABASE" in SUPABASE_URL or "YOUR_SERVICE" in SUPABASE_SERVICE_KEY:
        print("\n  [!] You haven't set your Supabase credentials.")
        print("      Edit migrate_to_supabase.py and replace:")
        print("        YOUR_SUPABASE_URL_HERE  → your project URL")
        print("        YOUR_SERVICE_KEY_HERE   → your service_role key")
        print("\n      Or set environment variables:")
        print("        set SUPABASE_URL=https://xxxx.supabase.co")
        print("        set SUPABASE_SERVICE_KEY=eyJhbGci...")
        sys.exit(1)


def test_connection():
    """Verify we can reach the Supabase API."""
    # Strip any trailing slash from URL
    base = SUPABASE_URL.rstrip('/')
    url  = f"{base}/rest/v1/legends?select=count"
    print(f"  Connecting to: {base}")
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        print(f"  Response: HTTP {r.status_code}")
        if r.status_code == 200:
            print("  ✓ Connected to Supabase")
            return True
        elif r.status_code == 404:
            print("  [!] Table 'legends' not found.")
            print("      Check in Supabase → Table Editor that the 'legends' table exists.")
            print("      If it doesn't, run supabase_setup.sql in the SQL Editor.")
            sys.exit(1)
        elif r.status_code == 401:
            print("  [!] Authentication failed — check your service_role key is correct.")
            print(f"      Key starts with: {SUPABASE_SERVICE_KEY[:20]}...")
            sys.exit(1)
        elif r.status_code == 400:
            print("  [!] Bad request — the URL may be incorrect.")
            print(f"      Tried: {url}")
            print(f"      Response: {r.text[:200]}")
            sys.exit(1)
        else:
            print(f"  [!] Unexpected response: HTTP {r.status_code}")
            print(f"      Response: {r.text[:200]}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"  [!] Could not connect to {base}")
        print("      Check the URL is correct and you have internet access.")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"  [!] Connection timed out.")
        sys.exit(1)


def load_legends():
    if not os.path.exists(LEGENDS_FILE):
        print(f"  [!] {LEGENDS_FILE} not found.")
        print("      Run build_legends.py --seed-only first to generate it.")
        sys.exit(1)
    with open(LEGENDS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("legends", data)


def upsert_batch(batch):
    """Insert or update a batch of legend rows."""
    url  = f"{SUPABASE_URL.rstrip('/')}/rest/v1/legends?on_conflict=name"
    rows = [
        {
            "name":     leg["name"],
            "lat":      leg["lat"],
            "lng":      leg["lng"],
            "category": leg.get("category", "beast"),
            "region":   leg.get("region", "Britain"),
            "summary":  leg.get("summary", ""),
            "source":   leg.get("source", ""),
        }
        for leg in batch
    ]
    r = requests.post(url, headers=get_headers(), json=rows, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  [!] Batch failed: HTTP {r.status_code} — {r.text[:200]}")
        return False
    return True


def migrate():
    print("\n  Folklore Map — Supabase migration")
    print("  " + "─" * 40)

    check_credentials()
    test_connection()

    legends = load_legends()
    total   = len(legends)
    print(f"\n  Migrating {total} legends in batches of {BATCH_SIZE} ...")

    success = 0
    failed  = 0

    for i in range(0, total, BATCH_SIZE):
        batch     = legends[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} rows) ...", end=" ")

        if upsert_batch(batch):
            success += len(batch)
            print("✓")
        else:
            failed += len(batch)
            print("✗")

        time.sleep(RATE_LIMIT)

    print(f"\n  Migration complete:")
    print(f"    Successful : {success}")
    print(f"    Failed     : {failed}")

    if failed == 0:
        print(f"\n  ✓ All {total} legends are now in Supabase.")
        print(f"    You can now use build_legends.py with --supabase flag")
        print(f"    and update index.html to fetch from Supabase.\n")
    else:
        print(f"\n  [!] Some rows failed. Check the errors above and re-run.")
        print(f"      The script is safe to re-run — it upserts on conflict.\n")


if __name__ == "__main__":
    migrate()
