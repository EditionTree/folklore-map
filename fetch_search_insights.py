# -*- coding: utf-8 -*-
"""
fetch_search_insights.py — pull Google Search Console performance data and write
a short, prioritised report the daily research/QC agents can act on.

This is a lightweight signal pipe, NOT an analytics platform: it stores only
aggregate query/page metrics from Search Console (no visitor-level data) and
turns them into a to-do list (titles to rewrite, pages to nudge onto page 1,
search terms we don't cover yet).

Auth: two supported methods (OAuth is preferred; service account is a fallback).

  OAuth 2.0 user login (recommended — works even when org policy blocks
  service-account keys):
    - In Google Cloud, configure the OAuth consent screen (External, Testing)
      and add your own Google account as a test user.
    - Create an OAuth client ID of type "Desktop app" and download its JSON.
    - Save it as ./gsc-oauth-client.json (or set GSC_OAUTH_CLIENT_JSON).
    - First run opens a browser to authorise; a refresh token is cached at
      ./gsc-token.json so later runs are non-interactive.
    - The Google account you log in with must have access to the property in
      Search Console (you, the owner, already do).
    - Requires: pip install google-auth google-auth-oauthlib requests

  Service account (only if your org allows downloadable keys):
    - Create a service account in Google Cloud and download its JSON key.
    - In Search Console → Settings → Users and permissions, add the service
      account's email as a Restricted user on the property.
    - Point GSC_SERVICE_ACCOUNT_JSON at the key file (or place it at
      ./gsc-service-account.json).

Both key files are git-ignored. Enable the "Google Search Console API" for the
project either way.

Env vars:
  GSC_OAUTH_CLIENT_JSON     path to the OAuth client secret (default: ./gsc-oauth-client.json)
  GSC_TOKEN_JSON            path to the cached user token (default: ./gsc-token.json)
  GSC_SERVICE_ACCOUNT_JSON  path to a service-account key (default: ./gsc-service-account.json)
  GSC_SITE_URL              property, e.g. "https://folklorefinder.uk/" (URL-prefix)
                            or "sc-domain:folklorefinder.uk" (domain property).
                            Default: https://folklorefinder.uk/

Usage:
  python fetch_search_insights.py            # fetch from GSC and write the report
  python fetch_search_insights.py --sample   # write a report from sample data (no creds; for testing)
"""
import os, io, sys, json, datetime, urllib.parse

BASE = "https://folklorefinder.uk"
OUT_DIR = "search-insights"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
DEFAULT_KEY_FILE = "gsc-service-account.json"
DEFAULT_OAUTH_CLIENT = "gsc-oauth-client.json"
DEFAULT_TOKEN_FILE = "gsc-token.json"

# Low-traffic-friendly thresholds. Raise these as traffic grows.
MIN_IMPR_TITLE = 25      # pages with at least this many impressions ...
MAX_CTR_TITLE = 0.02     # ... and CTR below this are title/summary candidates
NEARMISS_MIN_POS = 8.0   # "page 2" band: average position ...
NEARMISS_MAX_POS = 20.0  # ... in this range
NEARMISS_MIN_IMPR = 8
ZEROCLICK_MIN_IMPR = 15
TOP_N = 20


def _env(name, default=""):
    return (os.getenv(name) or default).strip().strip("\"'")


def date_window(lag_days=3, span_days=28):
    """GSC data lags a couple of days, so end the window `lag_days` back."""
    end = datetime.date.today() - datetime.timedelta(days=lag_days)
    start = end - datetime.timedelta(days=span_days - 1)
    return start.isoformat(), end.isoformat()


def oauth_credentials(client_file, token_file):
    """Return user OAuth credentials, refreshing or running the consent flow as
    needed. The refresh token is cached at token_file so later runs are silent."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GAuthRequest
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, [SCOPE])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GAuthRequest())
        else:
            if not os.path.exists(client_file):
                sys.exit(f"OAuth client file not found: {client_file}\n"
                         "Download a 'Desktop app' OAuth client JSON from Google Cloud "
                         "and save it there (or set GSC_OAUTH_CLIENT_JSON).")
            flow = InstalledAppFlow.from_client_secrets_file(client_file, [SCOPE])
            # Opens a browser once; falls back to a console URL on headless boxes.
            creds = flow.run_local_server(port=0)
        with io.open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def service_account_credentials(key_file):
    """Return service-account credentials (fallback when org policy allows keys)."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GAuthRequest
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=[SCOPE])
    creds.refresh(GAuthRequest())
    return creds


def get_credentials():
    """Pick an auth method: OAuth if a client file is present, else a service
    account key, else explain what to set up."""
    oauth_client = _env("GSC_OAUTH_CLIENT_JSON", DEFAULT_OAUTH_CLIENT)
    token_file = _env("GSC_TOKEN_JSON", DEFAULT_TOKEN_FILE)
    key_file = _env("GSC_SERVICE_ACCOUNT_JSON", DEFAULT_KEY_FILE)
    # Prefer an existing cached token, then an OAuth client, then a service key.
    if os.path.exists(token_file) or os.path.exists(oauth_client):
        return oauth_credentials(oauth_client, token_file)
    if os.path.exists(key_file):
        return service_account_credentials(key_file)
    sys.exit("No credentials found. Set up OAuth (save the Desktop-app client as ./"
             + DEFAULT_OAUTH_CLIENT + ") or place a service-account key at ./"
             + DEFAULT_KEY_FILE + ".  Or run with --sample to preview the format.")


def list_sites(creds):
    """Return the Search Console properties this account can see (siteEntry list)."""
    import requests
    r = requests.get("https://searchconsole.googleapis.com/webmasters/v3/sites",
                     headers={"Authorization": "Bearer " + creds.token}, timeout=60)
    r.raise_for_status()
    return r.json().get("siteEntry", [])


def resolve_site(creds, preferred):
    """Pick which property to query. Use `preferred` if the account can access it;
    otherwise auto-detect the folklorefinder property (domain OR URL-prefix form).
    If nothing matches, list what the account CAN see so the cause is obvious."""
    sites = list_sites(creds)
    usable = [s for s in sites if s.get("permissionLevel") != "siteUnverifiedUser"]
    urls = [s["siteUrl"] for s in usable]
    if preferred and preferred in urls:
        return preferred
    for u in urls:
        if "folklorefinder.uk" in u:
            return u
    listing = "\n".join("  - " + s["siteUrl"] + "  (" + s.get("permissionLevel", "?") + ")"
                        for s in sites) or "  (this account has no properties)"
    sys.exit("No accessible folklorefinder.uk property for the account you logged in with.\n"
             "Properties this account CAN see:\n" + listing +
             "\n\nFix: in Search Console, confirm folklorefinder.uk is added & verified "
             "under the SAME Google account you authorised with.")


def fetch_gsc(site_url, creds, start, end):
    """Return (page_rows, query_rows) from the Search Analytics API."""
    import requests
    endpoint = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
                + urllib.parse.quote(site_url, safe="") + "/searchAnalytics/query")
    headers = {"Authorization": "Bearer " + creds.token, "Content-Type": "application/json"}

    def query(dimensions):
        body = {"startDate": start, "endDate": end, "dimensions": dimensions, "rowLimit": 1000}
        r = requests.post(endpoint, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        return r.json().get("rows", [])

    return query(["page"]), query(["query"])


def _row(r):
    """Normalise an API row to a flat dict."""
    return {
        "key": r["keys"][0],
        "clicks": r.get("clicks", 0),
        "impressions": r.get("impressions", 0),
        "ctr": r.get("ctr", 0.0),
        "position": r.get("position", 0.0),
    }


def load_known_terms():
    """Legend names + tags, lowercased word set, to spot search terms we don't cover."""
    try:
        d = json.load(io.open("legends.json", encoding="utf-8"))
    except Exception:
        return set(), []
    words, names = set(), []
    for leg in d.get("legends", []):
        nm = leg.get("name", "")
        names.append(nm.lower())
        for w in nm.lower().replace("'", " ").replace("-", " ").split():
            if len(w) > 2:
                words.add(w)
        for t in leg.get("tags") or []:
            for w in t.lower().replace("-", " ").split():
                if len(w) > 2:
                    words.add(w)
    return words, names


def short(url):
    return url.replace(BASE, "") or url


def build_report(page_rows, query_rows, start, end):
    pages = [_row(r) for r in page_rows]
    queries = [_row(r) for r in query_rows]
    known_words, known_names = load_known_terms()

    title_cands = sorted(
        [p for p in pages if p["impressions"] >= MIN_IMPR_TITLE and p["ctr"] < MAX_CTR_TITLE],
        key=lambda p: -p["impressions"])[:TOP_N]
    near_miss = sorted(
        [p for p in pages if NEARMISS_MIN_POS <= p["position"] <= NEARMISS_MAX_POS
         and p["impressions"] >= NEARMISS_MIN_IMPR],
        key=lambda p: -p["impressions"])[:TOP_N]
    zero_click = sorted(
        [q for q in queries if q["clicks"] == 0 and q["impressions"] >= ZEROCLICK_MIN_IMPR],
        key=lambda q: -q["impressions"])[:TOP_N]

    def is_uncovered(term):
        t = term.lower()
        if any(t in nm or nm in t for nm in known_names):
            return False
        toks = [w for w in t.replace("'", " ").replace("-", " ").split() if len(w) > 2]
        return bool(toks) and not any(w in known_words for w in toks)

    uncovered = sorted(
        [q for q in queries if is_uncovered(q["key"])],
        key=lambda q: -q["impressions"])[:TOP_N]

    top_queries = sorted(queries, key=lambda q: -q["impressions"])[:TOP_N]

    L = []
    L.append(f"# Search insights — {start} to {end}")
    L.append("")
    L.append(f"_Generated {datetime.date.today().isoformat()} from Google Search Console. "
             "Aggregate query/page metrics only — no visitor data._")
    L.append("")

    L.append("## 1. Rewrite titles / summaries (high impressions, low CTR)")
    L.append("_These pages are shown often but rarely clicked — usually a weak title or summary._")
    if title_cands:
        for p in title_cands:
            L.append(f"- `{short(p['key'])}` — {int(p['impressions'])} impressions, "
                     f"{p['ctr']*100:.1f}% CTR, avg pos {p['position']:.1f}")
    else:
        L.append("- (none above threshold yet)")
    L.append("")

    L.append("## 2. Nudge onto page 1 (ranking ~position 8–20)")
    L.append("_Small, targeted content edits could move these up to where the clicks are._")
    if near_miss:
        for p in near_miss:
            L.append(f"- `{short(p['key'])}` — avg pos {p['position']:.1f}, "
                     f"{int(p['impressions'])} impressions, {int(p['clicks'])} clicks")
    else:
        L.append("- (none in band yet)")
    L.append("")

    L.append("## 3. Search terms we may not cover")
    L.append("_Queries whose words don't match any legend name or tag — candidate alt-names or new entries._")
    if uncovered:
        for q in uncovered:
            L.append(f"- \"{q['key']}\" — {int(q['impressions'])} impressions, {int(q['clicks'])} clicks")
    else:
        L.append("- (none detected)")
    L.append("")

    L.append("## 4. Zero-click queries (impressions, no clicks)")
    if zero_click:
        for q in zero_click:
            L.append(f"- \"{q['key']}\" — {int(q['impressions'])} impressions, avg pos {q['position']:.1f}")
    else:
        L.append("- (none above threshold yet)")
    L.append("")

    L.append("## 5. Top queries (visibility overview)")
    if top_queries:
        for q in top_queries:
            L.append(f"- \"{q['key']}\" — {int(q['impressions'])} impr, {int(q['clicks'])} clicks, "
                     f"{q['ctr']*100:.1f}% CTR, pos {q['position']:.1f}")
    else:
        L.append("- (no data yet)")
    L.append("")
    return "\n".join(L) + "\n"


SAMPLE_PAGES = [
    {"keys": [BASE + "/legends/black-shuck"], "clicks": 6, "impressions": 1840, "ctr": 0.0033, "position": 6.4},
    {"keys": [BASE + "/legends/barghest"], "clicks": 9, "impressions": 320, "ctr": 0.028, "position": 11.2},
    {"keys": [BASE + "/legends/lambton-worm"], "clicks": 40, "impressions": 900, "ctr": 0.044, "position": 4.1},
]
SAMPLE_QUERIES = [
    {"keys": ["black shuck"], "clicks": 30, "impressions": 1200, "ctr": 0.025, "position": 3.2},
    {"keys": ["barguest"], "clicks": 0, "impressions": 210, "ctr": 0.0, "position": 14.0},
    {"keys": ["norfolk ghost dog"], "clicks": 0, "impressions": 40, "ctr": 0.0, "position": 18.7},
    {"keys": ["lambton worm"], "clicks": 38, "impressions": 700, "ctr": 0.054, "position": 3.9},
]


def main():
    sample = "--sample" in sys.argv
    start, end = date_window()
    if sample:
        page_rows, query_rows = SAMPLE_PAGES, SAMPLE_QUERIES
    else:
        creds = get_credentials()
        # If GSC_SITE_URL is set, honour it; otherwise auto-detect the property
        # (domain vs URL-prefix) from the account's accessible sites.
        site_url = resolve_site(creds, _env("GSC_SITE_URL") or None)
        print("Using Search Console property:", site_url)
        page_rows, query_rows = fetch_gsc(site_url, creds, start, end)

    os.makedirs(OUT_DIR, exist_ok=True)
    report = build_report(page_rows, query_rows, start, end)
    with io.open(os.path.join(OUT_DIR, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    with io.open(os.path.join(OUT_DIR, "gsc-latest.json"), "w", encoding="utf-8") as f:
        json.dump({"start": start, "end": end, "pages": page_rows, "queries": query_rows},
                  f, ensure_ascii=False, indent=0)
    print(f"Wrote {OUT_DIR}/report.md ({len(page_rows)} pages, {len(query_rows)} queries"
          + (", SAMPLE data" if sample else "") + ")")


if __name__ == "__main__":
    main()
