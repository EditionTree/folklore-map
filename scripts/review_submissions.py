#!/usr/bin/env python3
"""Safely review submitted content: legend submissions, feedback, bug reports.

    export SUPABASE_URL=https://canjzkpvjwvkbjcduaaj.supabase.co
    export SUPABASE_SERVICE_KEY=...          # never commit this
    python scripts/review_submissions.py
    python scripts/review_submissions.py --all          # include actioned items
    python scripts/review_submissions.py --set-status legend_submissions <id> rejected

Everything a stranger typed is treated as hostile. Three rules this tool exists
to enforce, because they are easy to break by hand:

1. NOTHING IS EVER FETCHED. Submitted URLs are analysed lexically and printed as
   inert text. Fetching one would leak your IP to whoever submitted it, confirm
   you read it, and hand them a request originating from your machine. If the
   backend is ever changed to fetch submitted URLs, SSRF controls go in first.

2. Text is printed with invisible characters made visible. Bidi overrides can
   make "moc.live//:sptth" render as "https://evil.com" reversed, so a hostile
   URL can display as a friendly one. Control characters and zero-width joiners
   are escaped here rather than passed to your terminal.

3. Hostnames are decoded. A punycode host is shown in both forms, and mixed
   scripts are flagged: "аpple.com" with a Cyrillic а is a different site to
   "apple.com" and they are indistinguishable on screen.

Open any link you do decide to visit in a browser profile that is NOT signed in
to Cloudflare, GitHub or Supabase. See SUBMISSION_REVIEW.md.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


def _clean_env(name: str) -> str:
    """Match build_legends.py: tolerate values set with quotes preserved."""
    return os.getenv(name, "").strip().strip("\"'")


SUPABASE_URL = _clean_env("SUPABASE_URL") or "https://canjzkpvjwvkbjcduaaj.supabase.co"
SERVICE_KEY = _clean_env("SUPABASE_SERVICE_KEY")

# Same patterns the edge functions screen with, so what this tool calls
# suspicious matches what the `flagged` column already says.
INJECTION = [
    # The original pattern allowed exactly one word between the verb and the
    # noun, so "ignore all previous instructions" -- the commonest phrasing of
    # this attack -- was never caught. It missed 8 of 13 realistic phrasings on
    # test, while still firing on none of the folklore prose tested alongside.
    (r"\b(?:ignore|forget|disregard|override|bypass)\s+"
     r"(?:(?:the|all|any|your|these|those|of|previous|prior|above|earlier|preceding|system)\s+){0,4}"
     r"(?:instructions?|rules?|commands?|prompts?|directives?|guidelines?)",
     "prompt-injection phrasing"),
    (r"\b(DROP\s+TABLE|DELETE\s+FROM|TRUNCATE|INSERT\s+INTO|UPDATE\s+\w+\s+SET|ALTER\s+TABLE)",
     "SQL keywords"),
    (r"<script", "script tag"),
    (r"javascript:", "javascript: scheme"),
    (r"eval\s*\(", "eval("),
    (r"document\.write\s*\(", "document.write("),
    (r"on(load|click|error|mouseover)\s*=", "inline event handler"),
    (r"rm\s+-rf", "shell rm -rf"),
    (r"sudo\s+", "sudo"),
]

SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "cutt.ly", "shorturl.at", "tiny.cc", "lnkd.in", "rb.gy",
    "s.id", "t.ly", "shorte.st", "adf.ly", "bl.ink", "trib.al",
}

# Characters that reorder or hide text in a terminal or a browser.
DANGEROUS_INVISIBLES = {
    "‪": "LRE", "‫": "RLE", "‬": "PDF", "‭": "LRO",
    "‮": "RLO", "⁦": "LRI", "⁧": "RLI", "⁨": "FSI",
    "⁩": "PDI", "​": "ZWSP", "‌": "ZWNJ", "‍": "ZWJ",
    "⁠": "WJ", "﻿": "BOM", "­": "SHY",
}

TABLES = {
    "legend_submissions": {
        "pending": ["pending", "flagged"],
        "fields": ["legend_name", "region", "description", "source_url"],
        "urls": ["source_url"],
    },
    "feedback": {
        "pending": ["new", "reviewed", "needs_follow_up"],
        "fields": ["feedback_type", "message", "contact_email",
                   "related_legend", "related_collection", "page_url"],
        "urls": ["page_url"],
    },
    "bug_reports": {
        "pending": ["new"],
        "fields": ["description", "steps", "url", "browser", "device"],
        "urls": ["url"],
    },
}

# A homograph domain decodes to non-ASCII, and a Windows console defaulting to
# cp1252 raises UnicodeEncodeError on it. That would crash this tool on exactly
# the input it exists to detect, so force UTF-8 out and fall back to escapes
# rather than dying. An escaped codepoint is informative in its own right.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except (AttributeError, ValueError):
    pass

# Colour only when writing to a terminal, so piping to a file or a pager does
# not fill it with escape sequences.
if sys.stdout.isatty() and os.getenv("NO_COLOR") is None:
    RESET, BOLD, RED, YELLOW, DIM = "\033[0m", "\033[1m", "\033[31m", "\033[33m", "\033[2m"
else:
    RESET = BOLD = RED = YELLOW = DIM = ""


def api(method, path, body=None):
    if not SERVICE_KEY:
        sys.exit("SUPABASE_SERVICE_KEY is not set. This tool needs the service role "
                 "key to read submissions; export it, do not commit it.")
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
            return json.loads(text) if text.strip() else []
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def visible(s):
    """Render a string with anything invisible or reordering made explicit."""
    if s is None:
        return f"{DIM}(none){RESET}"
    out, notes = [], []
    for ch in str(s):
        if ch in DANGEROUS_INVISIBLES:
            tag = DANGEROUS_INVISIBLES[ch]
            out.append(f"{RED}<{tag}>{RESET}")
            notes.append(tag)
        elif unicodedata.category(ch) in ("Cc", "Cf") and ch not in "\n\t":
            out.append(f"{RED}<U+{ord(ch):04X}>{RESET}")
            notes.append(f"U+{ord(ch):04X}")
        else:
            out.append(ch)
    rendered = "".join(out)
    if notes:
        rendered += f"  {RED}[contains {', '.join(sorted(set(notes)))}]{RESET}"
    return rendered


def scripts_in(text):
    """Rough Unicode script names present, for homograph detection."""
    found = set()
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        found.add(name.split()[0])
    return found


def analyse_url(raw):
    """Lexical analysis only. This function never opens a connection."""
    warnings = []
    if not raw:
        return None, warnings
    try:
        u = urllib.parse.urlsplit(raw)
    except ValueError as e:
        return None, [f"unparseable URL ({e})"]

    if u.scheme not in ("http", "https"):
        warnings.append(f"scheme is {u.scheme or 'missing'}, not http/https")
    if u.username or u.password:
        warnings.append("URL embeds credentials before the host, which hides the real destination")

    host = (u.hostname or "").lower()
    decoded = host
    if host.startswith("xn--") or ".xn--" in host:
        try:
            decoded = host.encode("ascii").decode("idna")
            warnings.append(f"punycode host, decodes to: {decoded}")
        except Exception:
            warnings.append("punycode host that failed to decode")

    found = scripts_in(decoded)
    if len(found) > 1:
        warnings.append(f"host mixes scripts ({', '.join(sorted(found))}), possible lookalike")
    if host in SHORTENERS:
        warnings.append("URL shortener, the real destination is hidden")
    if re.fullmatch(r"[\d.]+|\[[0-9a-f:]+\]", host or ""):
        warnings.append("host is a bare IP address")
    if u.port and u.port not in (80, 443):
        warnings.append(f"non-standard port {u.port}")
    if len(raw) > 300:
        warnings.append(f"unusually long URL ({len(raw)} chars)")
    return {"scheme": u.scheme, "host": host, "decoded": decoded,
            "path": u.path, "query": u.query}, warnings


def screen(text):
    return [label for pattern, label in INJECTION
            if text and re.search(pattern, text, re.I)]


def show(table, cfg, row):
    print(f"\n{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}{table}{RESET}  id={row.get('id')}  "
          f"status={row.get('status')}  created={row.get('created_at', '')[:19]}")
    if row.get("flagged"):
        print(f"{RED}{BOLD}FLAGGED BY THE ENDPOINT: {row.get('flagged_reason')}{RESET}")
    print("-" * 72)

    all_text = " ".join(str(row.get(f) or "") for f in cfg["fields"])
    for field in cfg["fields"]:
        print(f"  {field:20} {visible(row.get(field))}")

    hits = screen(all_text)
    if hits:
        print(f"\n  {RED}suspicious patterns: {', '.join(hits)}{RESET}")

    for field in cfg["urls"]:
        raw = row.get(field)
        if not raw:
            continue
        parts, warns = analyse_url(raw)
        print(f"\n  {BOLD}URL in {field}{RESET}  {DIM}(not fetched, never fetched){RESET}")
        if parts:
            print(f"    host    {BOLD}{visible(parts['decoded'])}{RESET}")
            if parts["decoded"] != parts["host"]:
                print(f"    ascii   {parts['host']}")
            print(f"    scheme  {parts['scheme']}")
            if parts["path"]:
                print(f"    path    {visible(parts['path'][:120])}")
            if parts["query"]:
                print(f"    query   {visible(parts['query'][:120])}")
        for w in warns:
            print(f"    {YELLOW}! {w}{RESET}")
        if not warns:
            print(f"    {DIM}no lexical warnings (this is not an endorsement){RESET}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="include already-actioned rows")
    ap.add_argument("--table", choices=sorted(TABLES), help="restrict to one table")
    ap.add_argument("--set-status", nargs=3, metavar=("TABLE", "ID", "STATUS"),
                    help="update one row's status, e.g. --set-status feedback 3 actioned")
    args = ap.parse_args()

    if args.set_status:
        table, row_id, status = args.set_status
        if table not in TABLES:
            sys.exit(f"unknown table {table}")
        api("PATCH", f"{table}?id=eq.{urllib.parse.quote(row_id)}", {"status": status})
        print(f"{table} {row_id} -> {status}")
        return

    print(f"{BOLD}Submitted content is hostile until proven otherwise.{RESET}")
    print("No URL below has been fetched. If you open one, use a browser profile")
    print("that is not signed in to Cloudflare, GitHub or Supabase.")

    total = 0
    for table, cfg in TABLES.items():
        if args.table and table != args.table:
            continue
        query = "select=*&order=created_at.desc"
        if not args.all:
            statuses = ",".join(f'"{s}"' for s in cfg["pending"])
            query += f"&status=in.({statuses})"
        rows = api("GET", f"{table}?{query}")
        for row in rows:
            show(table, cfg, row)
        total += len(rows)
        if not rows:
            print(f"\n{DIM}{table}: nothing waiting{RESET}")

    print(f"\n{BOLD}{total} item(s).{RESET}")
    if total:
        print(f"Mark one done with: python scripts/review_submissions.py "
              f"--set-status <table> <id> <status>")


if __name__ == "__main__":
    main()
