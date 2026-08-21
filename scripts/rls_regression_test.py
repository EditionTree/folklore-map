#!/usr/bin/env python3
"""RLS / least-privilege regression tests for the Folklore Finder Supabase project.

Run this after any migration, and quarterly regardless:

    python scripts/rls_regression_test.py

It tests the live REST API as an anonymous browser would, using the same
published key that ships in map.html. That is deliberate: testing through
PostgREST checks what an attacker can actually reach, which is not always what
the grant tables imply. Two examples this suite exists because of:

  * A DELETE against a table anon cannot delete from returns 204, not 403 --
    RLS makes the rows invisible, so "0 rows affected" looks like success.
    Status codes alone are not evidence; assert on what the data does.
  * anon held TRUNCATE on public.legends for months. RLS does not apply to
    TRUNCATE, and the only thing preventing it was PostgREST exposing no verb
    that reaches it. Grants, not policies, are the control there.

No dependencies beyond the standard library, so it runs anywhere.
Exit code 0 = all passed, 1 = at least one failure.
"""

import json
import sys
import urllib.error
import urllib.request

PROJECT = "canjzkpvjwvkbjcduaaj"
BASE = f"https://{PROJECT}.supabase.co"
REST = f"{BASE}/rest/v1"
FUNCTIONS = f"{BASE}/functions/v1"
ORIGIN = "https://folklorefinder.uk"

# The published key from map.html. Public by design; it is the whole point of
# this suite that holding it grants almost nothing.
PUBLISHABLE_KEY = "sb_publishable_-XlJB_bYZlSjHAn7rQ2MQQ_BFsS5-4v"

# Exactly what the website reads. If a column is added to public.legends it must
# NOT appear here unless it is genuinely public; that is what the view is for.
EXPECTED_PUBLIC_COLUMNS = {
    "name", "lat", "lng", "category", "region", "summary", "source",
    "tags", "period", "cultural_tradition", "alt_names",
}

# Columns that exist on public.legends but must never be reachable through the
# public view. Extend this list whenever a private column is added.
MUST_NOT_BE_EXPOSED = [
    "id", "detail", "created_at", "updated_at", "date_added",
    "origin_date", "earliest_record", "historical_setting",
    "origin_type", "dating_confidence",
]

PRIVATE_TABLES = ["legends", "bug_reports", "feedback",
                  "legend_submissions", "analytics_events"]

failures: list[str] = []
passes = 0


def request(method, url, body=None, headers=None):
    """Return (status, text). Never raises on an HTTP error status."""
    hdrs = {
        "apikey": PUBLISHABLE_KEY,
        "Authorization": f"Bearer {PUBLISHABLE_KEY}",
        "Origin": ORIGIN,
        "Content-Type": "application/json",
    }
    hdrs.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # network problem, not a policy result
        return 0, str(e)


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  PASS  {name}")
    else:
        failures.append(f"{name} :: {detail}")
        print(f"  FAIL  {name}\n          {detail}")


print("Anonymous read access")

status, text = request("GET", f"{REST}/public_legends?select=name&limit=5")
check("anon can read public_legends", status == 200, f"got HTTP {status}: {text[:120]}")

rows = json.loads(text) if status == 200 and text.startswith("[") else []
check("public_legends returns rows", len(rows) > 0, f"got {len(rows)} rows")

status, text = request("GET", f"{REST}/public_legends?select=*&limit=1")
cols = set(json.loads(text)[0].keys()) if status == 200 and text.startswith("[") else set()
check(
    "public_legends exposes exactly the expected columns",
    cols == EXPECTED_PUBLIC_COLUMNS,
    f"unexpected: {sorted(cols - EXPECTED_PUBLIC_COLUMNS)} | "
    f"missing: {sorted(EXPECTED_PUBLIC_COLUMNS - cols)}",
)

print("\nPrivate tables are unreachable")

for table in PRIVATE_TABLES:
    status, text = request("GET", f"{REST}/{table}?select=*&limit=1")
    readable = status == 200 and text.startswith("[") and json.loads(text)
    check(f"anon cannot read {table}", not readable,
          f"HTTP {status} returned data: {text[:120]}")

print("\nPrivate columns are not reachable through the view")

for col in MUST_NOT_BE_EXPOSED:
    status, text = request("GET", f"{REST}/public_legends?select={col}&limit=1")
    check(f"public_legends does not expose {col}", status != 200,
          f"HTTP {status} returned it: {text[:100]}")

print("\nAnonymous writes are refused")

# A write that "succeeds" with 0 rows affected still proves nothing, so where a
# status could be ambiguous the row count is checked afterwards instead.
status, text = request("POST", f"{REST}/public_legends",
                       body={"name": "__rls_probe__", "lat": 0, "lng": 0})
check("anon cannot insert via the view", status >= 400, f"got HTTP {status}: {text[:120]}")

status, text = request("POST", f"{REST}/legends",
                       body={"name": "__rls_probe__", "lat": 0, "lng": 0})
check("anon cannot insert into the base table", status >= 400, f"got HTTP {status}: {text[:120]}")

status, text = request("PATCH", f"{REST}/legends?name=eq.Black%20Shuck",
                       body={"summary": "__rls_probe__"})
check("anon cannot update the base table", status >= 400, f"got HTTP {status}: {text[:120]}")

request("DELETE", f"{REST}/legends?name=eq.__rls_probe__")
status, text = request("GET", f"{REST}/public_legends?select=name&limit=2000")
count = len(json.loads(text)) if status == 200 and text.startswith("[") else -1
check("legend count is intact after write attempts", count > 0,
      f"public_legends now returns {count} rows")

print("\nEdge functions still validate")

status, text = request("POST", f"{FUNCTIONS}/submit-event",
                       body={"event_type": "__not_allowed__"})
check("submit-event rejects an unknown event_type", status == 400, f"got HTTP {status}")

status, text = request("POST", f"{FUNCTIONS}/submit-event",
                       body={"event_type": "legend_viewed",
                             "legend_name": "A" * 3000})
check("submit-event rejects an oversized body", status == 413, f"got HTTP {status}")

for fn, payload in [
    ("submit-feedback", {"feedback_type": "general", "message": "probe",
                         "cf_turnstile_response": "invalid"}),
    ("submit-bug", {"description": "probe", "cf_turnstile_response": "invalid"}),
    ("submit-legend", {"legend_name": "p", "region": "p", "description": "p",
                       "source_url": "https://example.com",
                       "cf_turnstile_response": "invalid"}),
]:
    status, _ = request("POST", f"{FUNCTIONS}/{fn}", body=payload)
    check(f"{fn} refuses an invalid Turnstile token", status == 403, f"got HTTP {status}")

for fn, payload in [
    ("submit-feedback", {"feedback_type": "general", "message": 1,
                         "cf_turnstile_response": "x"}),
    ("submit-bug", {"description": 1, "cf_turnstile_response": "x"}),
    ("submit-legend", {"legend_name": 1, "region": "p", "description": "p",
                       "source_url": "https://example.com",
                       "cf_turnstile_response": "x"}),
]:
    status, _ = request("POST", f"{FUNCTIONS}/{fn}", body=payload)
    check(f"{fn} handles a non-string field without a 500", status == 400, f"got HTTP {status}")

print(f"\n{passes} passed, {len(failures)} failed")
if failures:
    print("\nFailures:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
