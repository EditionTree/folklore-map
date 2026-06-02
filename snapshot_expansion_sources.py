#!/usr/bin/env python3
"""
One-off public-source snapshot for Folklore Map expansion research.

Stores compact metadata and short excerpts for review. It deliberately does
not modify legends.json, sync Supabase, or mirror full copyrighted articles.
"""

import argparse
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests


class HTMLParseError(RuntimeError):
    """Raised when a page cannot be parsed as usable HTML."""




USER_AGENT = "FolkloreMap-OneOffSnapshot/1.0 (research metadata snapshot)"
TIMEOUT = 25
RATE_LIMIT = 0.6
OUTPUT_DIR = Path("source_snapshots") / "one_off_expansion"
ROBOTS_CACHE = {}

FOLKLORE_TERMS = {
    "aquatic": ("mermaid", "kelpie", "selkie", "water spirit", "sea monster",
                "lake monster", "river spirit", "wreck", "drowned"),
    "dragon": ("dragon", "worm", "wyrm", "serpent"),
    "fairy": ("fairy", "faerie", "faery", "pixie", "piskie", "boggart",
              "goblin", "brownie", "changeling", "otherworld"),
    "ghost": ("ghost", "haunted", "haunting", "spectre", "apparition",
              "phantom", "poltergeist"),
    "giant": ("giant",),
    "legendary_site": ("standing stone", "stone circle", "dolmen", "cairn",
                       "barrow", "sacred site", "holy well", "burial mound",
                       "passage tomb", "megalith", "pagan"),
    "pirate": ("pirate", "privateer", "smuggler", "wrecking", "treasure"),
    "witch": ("witch", "witchcraft", "cunning folk"),
    "hero_or_deity": ("god", "goddess", "deity", "hero", "saint", "king arthur",
                      "merlin", "fionn", "cú chulainn", "mabinogi"),
    "custom": ("festival", "custom", "tradition", "ritual", "ballad", "folklore"),
}

UK_IRELAND_TERMS = (
    "britain", "british", "england", "english", "scotland", "scottish",
    "wales", "welsh", "ireland", "irish", "cornwall", "cornish", "orkney",
    "shetland", "manx", "isle of man", "celtic", "gaelic",
)


@dataclass
class Record:
    source: str
    title: str
    url: str
    excerpt: str = ""
    category_guess: str = ""
    matched_terms: tuple = ()
    existing_match: str = ""


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.title_parts = []
        self.text_parts = []
        self._href = None
        self._anchor_parts = []
        self._in_title = False
        self._skip_depth = 0


    def error(self, message):
        # Python 3.9's HTMLParser can still call ParserBase.error() for
        # malformed declarations, which raises NotImplementedError by default.
        # Raising a regular parsing exception lets parse_page recover or skip.
        raise HTMLParseError(message)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = attrs.get("href")
            self._anchor_parts = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            text = clean_text(" ".join(self._anchor_parts))
            self.links.append((self._href, text))
            self._href = None
            self._anchor_parts = []

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._href is not None:
            self._anchor_parts.append(data)
        self.text_parts.append(data)

    @property
    def title(self):
        return clean_text(" ".join(self.title_parts))

    @property
    def text(self):
        return clean_text(" ".join(self.text_parts))


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def short_excerpt(text, limit=420):
    text = clean_text(text)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def normalise_name(value):
    value = re.sub(r"[^a-z0-9 ]", "", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def load_existing_names():
    path = Path("legends.json")
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("legends", [])
    return {normalise_name(row["name"]): row["name"] for row in rows}


def classify(title, excerpt):
    text = f"{title} {excerpt}".lower()
    hits = []
    categories = []
    for category, terms in FOLKLORE_TERMS.items():
        matched = [term for term in terms if term in text]
        if matched:
            categories.append(category)
            hits.extend(matched)
    return (categories[0] if categories else "", tuple(sorted(set(hits))))


def make_record(source, title, url, excerpt="", existing_names=None):
    category, hits = classify(title, excerpt)
    existing_names = existing_names or {}
    return Record(
        source=source,
        title=clean_text(title),
        url=url,
        excerpt=short_excerpt(excerpt),
        category_guess=category,
        matched_terms=hits,
        existing_match=existing_names.get(normalise_name(title), ""),
    )


def fetch(session, url):
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    time.sleep(RATE_LIMIT)
    return response


def robots_allowed(session, url):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url in ROBOTS_CACHE:
        return ROBOTS_CACHE[robots_url].can_fetch(USER_AGENT, url)
    parser = RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.parse(fetch(session, robots_url).text.splitlines())
        ROBOTS_CACHE[robots_url] = parser
        return parser.can_fetch(USER_AGENT, url)
    except requests.RequestException:
        return True


def parse_html_text(html):
    parser = LinkParser()
    parser.feed(html)
    parser.close()
    return parser


def parse_page(session, url):
    response = fetch(session, url)
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "html" not in content_type and "text/plain" not in content_type:
        raise HTMLParseError(f"unsupported content type: {content_type}")

    try:
        return parse_html_text(response.text)
    except (HTMLParseError, NotImplementedError, AssertionError) as exc:
        # Some otherwise usable pages contain malformed declarations such as
        # broken <![...]> sections that Python 3.9's HTMLParser cannot digest.
        # Remove only those declarations and try once more before skipping.
        cleaned = re.sub(r"<!\[[^>]*>", "", response.text)
        try:
            return parse_html_text(cleaned)
        except (HTMLParseError, NotImplementedError, AssertionError) as retry_exc:
            raise HTMLParseError(f"HTML parse failed: {retry_exc}") from exc


def same_host(url, host):
    return urlparse(url).netloc.lower().removeprefix("www.") == host.removeprefix("www.")


def crawl_metadata(session, source, start_urls, max_pages, existing_names,
                   include_path_terms=(), candidate_only=False):
    queue = list(start_urls)
    start_set = set(start_urls)
    seen = set()
    records = []
    while queue and len(seen) < max_pages:
        url = urldefrag(queue.pop(0))[0]
        if not url or url in seen:
            continue
        host = urlparse(start_urls[0]).netloc.lower()
        if not same_host(url, host):
            continue
        path = urlparse(url).path.lower()
        if (url not in start_set and include_path_terms
                and not any(term in path for term in include_path_terms)):
            continue
        if not robots_allowed(session, url):
            print(f"  robots.txt skipped: {url}")
            continue
        seen.add(url)
        try:
            page = parse_page(session, url)
        except requests.RequestException as exc:
            print(f"  fetch failed: {url} ({exc})")
            continue
        except HTMLParseError as exc:
            print(f"  parse skipped: {url} ({exc})")
            continue
        record = make_record(source, page.title or url, url, page.text, existing_names)
        if not candidate_only or record.matched_terms:
            records.append(record)
        for href, _ in page.links:
            child = urldefrag(urljoin(url, href))[0]
            if child.startswith(("http://", "https://")) and same_host(child, host):
                queue.append(child)
    return records


def snapshot_gutendex(session, existing_names, max_pages):
    queries = [
        "british folklore", "english folklore", "scottish folklore",
        "welsh folklore", "irish folklore", "celtic folklore",
        "fairy tales", "ghost stories", "legends",
        "daemonologie", "malleus maleficarum", "gypsy folk tales",
        "romano lavo lil", "bampfylde moore carew", "gypsy lore society",
    ]
    records = []
    seen = set()
    for query in queries:
        url = f"https://gutendex.com/books/?search={requests.utils.quote(query)}"
        pages = 0
        while url and pages < max_pages:
            data = fetch(session, url).json()
            for book in data.get("results", []):
                book_id = book.get("id")
                if book_id in seen:
                    continue
                seen.add(book_id)
                authors = ", ".join(author.get("name", "") for author in book.get("authors", []))
                subjects = "; ".join(book.get("subjects", []))
                excerpt = f"Author: {authors}. Subjects: {subjects}"
                record = make_record(
                    "gutendex", book.get("title", f"Gutenberg book {book_id}"),
                    f"https://www.gutenberg.org/ebooks/{book_id}", excerpt,
                    existing_names,
                )
                records.append(record)
            url = data.get("next")
            pages += 1
    return records


def snapshot_encyclopedia_com(session, existing_names, max_pages):
    """
    Snapshot Encyclopedia.com's bounded Folklore and Mythology index.

    The category contains global mythology, so retain compact metadata for
    index entries and use British/Irish terms to narrow the review candidates.
    """
    base_url = (
        "https://www.encyclopedia.com/literature-and-arts/"
        "classical-literature-mythology-and-folklore/folklore-and-mythology"
    )
    records = []
    seen_urls = set()
    for page_number in range(max_pages):
        index_url = base_url if page_number == 0 else f"{base_url}?page={page_number}"
        if not robots_allowed(session, index_url):
            print(f"  robots.txt skipped: {index_url}")
            continue
        index_page = parse_page(session, index_url)
        entry_links = []
        for href, anchor_text in index_page.links:
            child = urldefrag(urljoin(index_url, href))[0]
            if not child.startswith("https://www.encyclopedia.com/"):
                continue
            path = urlparse(child).path
            if not path.startswith("/literature-and-arts/") or child == base_url:
                continue
            if "/folklore-and-mythology/" not in path:
                continue
            entry_links.append((child, anchor_text))
        if not entry_links:
            break
        for url, anchor_text in entry_links:
            if url in seen_urls or not robots_allowed(session, url):
                continue
            seen_urls.add(url)
            try:
                page = parse_page(session, url)
            except (requests.RequestException, HTMLParseError) as exc:
                print(f"  fetch skipped: {url} ({exc})")
                continue
            record = make_record(
                "encyclopedia_com",
                anchor_text or page.title or url,
                url,
                page.text,
                existing_names,
            )
            text = f"{record.title} {page.text}".lower()
            if any(term in text for term in UK_IRELAND_TERMS):
                records.append(record)
    return records


def write_snapshot(source, records):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source,
        "count": len(records),
        "records": [asdict(record) for record in records],
    }
    path = OUTPUT_DIR / f"{source}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path} ({len(records)} records)")


def write_candidate_report(all_records):
    candidates = []
    seen = set()
    for record in all_records:
        key = (record.source, record.url)
        if key in seen or not record.matched_terms or record.existing_match:
            continue
        seen.add(key)
        candidates.append(record)
    candidates.sort(key=lambda item: (item.category_guess, item.source, item.title))
    write_snapshot("review_candidates", candidates)


def write_manifest(statuses):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": "One-off public metadata snapshot for manual folklore-map review",
        "sources": statuses,
    }
    path = OUTPUT_DIR / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=120,
                        help="Maximum HTML pages per crawl source (default: 120)")
    parser.add_argument("--gutendex-pages", type=int, default=3,
                        help="Maximum result pages per Gutendex query (default: 3)")
    parser.add_argument("--encyclopedia-pages", type=int, default=17,
                        help="Maximum Encyclopedia.com index pages (default: 17)")
    parser.add_argument("--source", action="append", choices=[
        "folklore_society", "gutendex", "sacred_texts", "historic_uk",
        "folklore_library", "olde_chronicles", "encyclopedia_com",
        "gypsy_lore_society",
    ], help="Limit to one or more named sources")
    args = parser.parse_args()

    selected = set(args.source or [
        "folklore_society", "gutendex", "sacred_texts", "historic_uk",
        "folklore_library", "olde_chronicles", "gypsy_lore_society",
    ])
    existing_names = load_existing_names()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    collected = []
    statuses = {}

    crawls = {
        "folklore_society": (
            ["https://www.folklore-society.com/site-map/"],
            ("resources", "library", "archive", "publications", "collections"),
        ),
        "sacred_texts": (
            [
                "https://sacred-texts.com/neu/celt/index.htm",
                "https://sacred-texts.com/neu/roma/gft/index.htm",
            ],
            ("/neu/celt/", "/neu/roma/"),
        ),
        "gypsy_lore_society": (
            ["https://onlinebooks.library.upenn.edu/webbin/serial?id=jgypsylore"],
            (),
        ),
        "historic_uk": (
            ["https://www.historic-uk.com/Sitemap/"],
            ("cultureuk", "historyuk", "folklore", "myths", "legends", "ghost"),
        ),
        "folklore_library": (
            ["https://www.folklorelibrary.com/"],
            ("archive", "collection", "explore", "folklore", "library"),
        ),
        "olde_chronicles": (
            ["https://oldechronicles.org.uk/browse_stories/"],
            (),
        ),
    }

    for source in sorted(selected):
        print(f"\n[{source}]")
        try:
            if source == "gutendex":
                records = snapshot_gutendex(session, existing_names, args.gutendex_pages)
            elif source == "encyclopedia_com":
                records = snapshot_encyclopedia_com(
                    session, existing_names, args.encyclopedia_pages
                )
            else:
                starts, terms = crawls[source]
                records = crawl_metadata(
                    session, source, starts, args.max_pages, existing_names,
                    include_path_terms=terms,
                )
        except (requests.RequestException, HTMLParseError) as exc:
            print(f"  source failed: {exc}")
            records = []
            statuses[source] = {"status": "failed", "error": str(exc), "count": 0}
        else:
            statuses[source] = {"status": "ok", "count": len(records)}
        write_snapshot(source, records)
        collected.extend(records)

    if selected == {"encyclopedia_com"}:
        encyclopedia_candidates = [
            record for record in collected
            if record.matched_terms and not record.existing_match
        ]
        write_snapshot("encyclopedia_com_review_candidates", encyclopedia_candidates)
    else:
        write_candidate_report(collected)
    write_manifest(statuses)
    print("\nDone. Review source_snapshots/one_off_expansion/review_candidates.json")


if __name__ == "__main__":
    main()
