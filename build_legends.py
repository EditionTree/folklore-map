#!/usr/bin/env python3
"""
build_legends.py — Folklore Map one-time data pipeline

Pulls UK folklore articles from Wikipedia categories, fetches summaries
and coordinates for each, merges with hand-curated seed data, and writes
a static legends.json for the map to consume.

This is a one-time build tool — run it once, review the output, and
commit legends.json. Folklore doesn't change.

Usage:
    python build_legends.py                  # full run
    python build_legends.py --seed-only      # skip Wikipedia, just write seed data
    python build_legends.py --verbose        # show each API call
    python build_legends.py --limit 50       # cap articles per category (testing)
"""

import argparse
import json
import time
import re
from datetime import datetime, timezone

import requests


WIKIPEDIA_API  = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIDATA_API   = "https://www.wikidata.org/w/api.php"
USER_AGENT     = "FolkloreMap-BuildScript/1.0 (one-time data build; https://github.com)"
TIMEOUT        = 20
RATE_LIMIT     = 0.3    # seconds between requests

# British Isles bounding box for coordinate sanity check
UK_BOUNDS = {"lat_min": 49.0, "lat_max": 61.5, "lng_min": -10.5, "lng_max": 2.5}  # includes Ireland and the Channel Islands


# ---------------------------------------------------------------------------
# Wikipedia categories to pull from — and which map category to assign them
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("Category:English_legendary_creatures",      "beast"),
    ("Category:Scottish_legendary_creatures",     "beast"),
    ("Category:Welsh_legendary_creatures",        "beast"),
    ("Category:British_legendary_creatures",      "beast"),
    ("Category:English_ghosts",                   "ghost"),
    ("Category:Scottish_ghosts",                  "ghost"),
    ("Category:Welsh_ghosts",                     "ghost"),
    ("Category:British_ghosts",                   "ghost"),
    ("Category:Fairies",                          "fairy"),
    ("Category:English_fairies",                  "fairy"),
    ("Category:Scottish_fairies",                 "fairy"),
    ("Category:Welsh_fairies",                    "fairy"),
    ("Category:Water_spirits",                    "water"),
    ("Category:Witchcraft_in_England",            "witch"),
    ("Category:Witchcraft_in_Scotland",           "witch"),
    ("Category:Lake_monsters",                    "water"),
    ("Category:Sea_monsters",                     "water"),
    ("Category:English_folklore",                 "beast"),
    ("Category:Scottish_folklore",                "beast"),
    ("Category:Welsh_folklore",                   "beast"),
    ("Category:Cornish_folklore",                 "beast"),
    ("Category:Folklore_of_Orkney",               "water"),
    ("Category:Manx_folklore",                    "fairy"),
    # Deities
    ("Category:Celtic_goddesses",                 "deity"),
    ("Category:Celtic_gods",                      "deity"),
    ("Category:British_gods",                     "deity"),
    ("Category:Scottish_mythology",               "deity"),
    ("Category:Welsh_mythology",                  "deity"),
    ("Category:Irish_mythology",                  "deity"),
    ("Category:Brythonic_mythology",              "deity"),
    ("Category:Gaelic_mythology",                 "deity"),
    ("Category:Anglo-Saxon_paganism",             "deity"),
    # Sacred sites & mythic locations
    ("Category:Sacred_sites_in_the_United_Kingdom", "location"),
    ("Category:Stone_circles_in_England",           "location"),
    ("Category:Stone_circles_in_Scotland",          "location"),
    ("Category:Stone_circles_in_Wales",             "location"),
    ("Category:Hill_figures_in_England",            "location"),
    ("Category:Arthurian_legend",                   "location"),
    ("Category:Submerged_settlements",              "location"),
    ("Category:Haunted_locations_in_England",       "location"),
    ("Category:Haunted_locations_in_Scotland",      "location"),
    ("Category:Haunted_castles_in_England",         "location"),
    ("Category:Haunted_castles_in_Scotland",        "location"),
    # Irish categories — expanded for British Isles coverage
    ("Category:Irish_legendary_creatures",          "beast"),
    ("Category:Irish_folklore",                     "fairy"),
    ("Category:Irish_ghosts",                       "ghost"),
    ("Category:Irish_fairies",                      "fairy"),
    ("Category:Mythological_creatures_of_Ireland",  "beast"),
    ("Category:Mythological_locations_in_Ireland",  "location"),
    ("Category:Irish_mythology",                    "deity"),
    ("Category:Ulster_Cycle",                       "deity"),
    ("Category:Fenian_Cycle",                       "deity"),
    ("Category:Mythological_Cycle",                 "deity"),
    ("Category:Tuatha_Dé_Danann",                   "deity"),
    ("Category:Fomorians",                          "deity"),
    ("Category:Irish_witchcraft",                   "witch"),
    ("Category:Haunted_locations_in_Ireland",       "location"),
    ("Category:Sacred_sites_in_Ireland",            "location"),
    ("Category:Megalithic_monuments_in_Ireland",    "location"),
    # Pirates, privateers and smuggling. Maritime folklore belongs under water.
    ("Category:English_pirates",                    "pirate"),
    ("Category:Scottish_pirates",                   "pirate"),
    ("Category:Irish_pirates",                      "pirate"),
    ("Category:Welsh_pirates",                      "pirate"),
    ("Category:Privateers",                         "pirate"),
    ("Category:British_pirates",                    "pirate"),
    ("Category:Smuggling_in_the_United_Kingdom",    "pirate"),
    ("Category:Maritime_folklore",                  "water"),
]

# ---------------------------------------------------------------------------
# Wikipedia list articles to pull members from
# Used for dragons and giants which live in list pages not categories
# Format: (list_article_title, category_to_assign)
# ---------------------------------------------------------------------------
LISTS = [
    ("List of dragons in mythology and legend",    "dragon"),
    ("List of giants in mythology and folklore",   "giant"),
    ("List of Arthurian characters",               "deity"),
    ("List of Irish mythological figures",         "deity"),
]

CATEGORY_LABELS = {
    "beast":    "Beasts",
    "ghost":    "Ghosts",
    "fairy":    "Fae & Spirits",
    "water":    "Aquatic Legends",
    "dragon":   "Dragons",
    "witch":    "Witches",
    "deity":    "Deities",
    "giant":    "Giants",
    "location": "Sacred Sites",
    "hero":     "Legendary Figures",
    # Renamed 2026-08-23 in js/categories.js; this fourth copy was missed and
    # still shipped "Pirates" into legends.json for nine days.
    "pirate":   "Pirates & Smugglers",
}

# Pirate biographies are admitted deliberately. Wikipedia categories also
# contain many ordinary privateers and naval figures whose history is not
# itself folklore.
PIRATE_FOLKLORE_TITLES = {
    "Anne Bonny",
    "Andrew Barton (privateer)",
    "Bartholomew Roberts",
    "Blackbeard",
    "Francis Drake",
    "Grace O'Malley",
    "Henry Every",
    "Henry Morgan",
    "Howell Davis",
    "Jack Ward",
    "John Gow",
    "Mary Read",
    "William Kidd",
}


# ---------------------------------------------------------------------------
# Seed data — hand-curated, always included, takes priority over API results
# ---------------------------------------------------------------------------
# SEED_LEGENDS is the hand-curated permanent dataset, stored in seeds.json
# (extracted from inline list 2026-06-03 for safer editing / agent management).
with open('seeds.json', encoding='utf-8') as _seed_f:
    SEED_LEGENDS = json.load(_seed_f)


# ---------------------------------------------------------------------------
# Wikipedia API functions
# ---------------------------------------------------------------------------

def get_category_members(category: str, limit: int, verbose: bool) -> list:
    """Fetch page titles from a Wikipedia category."""
    members = []
    params = {
        "action":   "query",
        "list":     "categorymembers",
        "cmtitle":  category,
        "cmlimit":  min(limit, 500),
        "cmtype":   "page",
        "cmnamespace": 0,
        "format":   "json"
    }
    try:
        r = requests.get(
            WIKIPEDIA_API,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT
        )
        r.raise_for_status()
        members = r.json().get("query", {}).get("categorymembers", [])
        if verbose:
            print(f"      {len(members)} articles found")
    except Exception as e:
        print(f"      [!] Failed: {e}")
    return members


def get_list_members(list_title: str, verbose: bool) -> list:
    """
    Extract linked article titles from a Wikipedia list article.
    Uses the links API to get all internal links from the page,
    which captures the individual entries in list articles.
    """
    members = []
    params = {
        "action":  "query",
        "titles":  list_title,
        "prop":    "links",
        "pllimit": 500,
        "plnamespace": 0,
        "format":  "json"
    }
    try:
        r = requests.get(
            WIKIPEDIA_API,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            links = page.get("links", [])
            for link in links:
                title = link.get("title", "")
                if title:
                    members.append({"title": title})
        if verbose:
            print(f"      {len(members)} linked articles found")
    except Exception as e:
        print(f"      [!] Failed: {e}")
    return members


def get_article_geodata(titles: list, verbose: bool) -> dict:
    """
    Fetch coordinates for a batch of article titles using Wikipedia's
    GeoData extension. Returns dict of title -> (lat, lng).
    """
    coords = {}
    # API accepts up to 50 titles at once
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        try:
            r = requests.get(
                WIKIPEDIA_API,
                params={
                    "action":   "query",
                    "titles":   "|".join(batch),
                    "prop":     "coordinates",
                    "format":   "json",
                    "colimit":  50,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT
            )
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                title = page.get("title", "")
                page_coords = page.get("coordinates", [])
                if page_coords:
                    lat = page_coords[0].get("lat")
                    lng = page_coords[0].get("lon")
                    if lat is not None and lng is not None:
                        coords[title] = (float(lat), float(lng))
            time.sleep(RATE_LIMIT)
        except Exception as e:
            if verbose:
                print(f"      [!] GeoData batch failed: {e}")
    return coords


def get_pirate_birthplace_geodata(titles: list, verbose: bool) -> dict:
    """
    Fetch birthplace coordinates for pirate biographies via Wikidata.
    Wikipedia biographies rarely expose page coordinates, so this fallback
    keeps British Isles-born pirates eligible for the map.
    """
    # Country-level birthplaces create misleading pins at national centroids.
    # Seeds can still override biographies with a stronger local association.
    generic_birthplaces = {
        "Q21",     # England
        "Q22",     # Scotland
        "Q25",     # Wales
        "Q27",     # Ireland
        "Q145",    # United Kingdom
        "Q23666",  # British Isles
    }
    title_to_item = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        try:
            r = requests.get(
                WIKIPEDIA_API,
                params={
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "pageprops",
                    "ppprop": "wikibase_item",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                item = page.get("pageprops", {}).get("wikibase_item")
                if item:
                    title_to_item[page.get("title", "")] = item
        except Exception as e:
            if verbose:
                print(f"      [!] Wikidata page mapping failed: {e}")

    item_to_title = {item: title for title, item in title_to_item.items()}
    birthplace_to_titles = {}
    for i in range(0, len(item_to_title), 50):
        batch = list(item_to_title)[i:i + 50]
        try:
            r = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": "claims",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            for item, entity in r.json().get("entities", {}).items():
                claims = entity.get("claims", {}).get("P19", [])
                if not claims:
                    continue
                value = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                birthplace = value.get("id")
                if birthplace and birthplace not in generic_birthplaces:
                    birthplace_to_titles.setdefault(birthplace, []).append(item_to_title[item])
        except Exception as e:
            if verbose:
                print(f"      [!] Wikidata birthplace lookup failed: {e}")

    coords = {}
    birthplaces = list(birthplace_to_titles)
    for i in range(0, len(birthplaces), 50):
        batch = birthplaces[i:i + 50]
        try:
            r = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": "claims",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            for birthplace, entity in r.json().get("entities", {}).items():
                claims = entity.get("claims", {}).get("P625", [])
                if not claims:
                    continue
                value = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                lat, lng = value.get("latitude"), value.get("longitude")
                if lat is None or lng is None:
                    continue
                for title in birthplace_to_titles.get(birthplace, []):
                    coords[title] = (float(lat), float(lng))
        except Exception as e:
            if verbose:
                print(f"      [!] Wikidata birthplace coordinates failed: {e}")

    if verbose:
        print(f"      {len(coords)} pirate biographies have birthplace coordinates")
    return coords


def get_article_summary(title: str, verbose: bool) -> str:
    """Fetch plain-text summary from Wikipedia REST API."""
    encoded = requests.utils.quote(title.replace(" ", "_"))
    try:
        r = requests.get(
            f"{WIKIPEDIA_REST}/{encoded}",
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT
        )
        if r.status_code == 404:
            return ""
        r.raise_for_status()
        extract = r.json().get("extract", "")
        # Trim to popup-friendly length
        if len(extract) > 450:
            # Try to cut at a sentence boundary
            cutoff = extract[:450].rfind(". ")
            extract = extract[:cutoff + 1] if cutoff > 200 else extract[:447] + "..."
        return extract
    except Exception:
        return ""


def is_in_uk(lat: float, lng: float) -> bool:
    """Rough bounding box check — filters out entries placed outside the British Isles."""
    return (UK_BOUNDS["lat_min"] <= lat <= UK_BOUNDS["lat_max"] and
            UK_BOUNDS["lng_min"] <= lng <= UK_BOUNDS["lng_max"])


def infer_region(title: str, summary: str) -> str:
    """
    Very rough region inference from article text.
    Good enough for display — can be manually corrected in legends.json.
    """
    text = (title + " " + summary).lower()
    regions = [
        ("cornwall",      "Cornwall"),
        ("devon",         "Devon"),
        ("yorkshire",     "Yorkshire"),
        ("lancashire",    "Lancashire"),
        ("norfolk",       "Norfolk"),
        ("suffolk",       "Suffolk"),
        ("orkney",        "Orkney"),
        ("shetland",      "Shetland"),
        ("highlands",     "Highland, Scotland"),
        ("highland",      "Highland, Scotland"),
        ("scottish",      "Scotland"),
        ("scotland",      "Scotland"),
        ("wales",         "Wales"),
        ("welsh",         "Wales"),
        ("ireland",       "Ireland"),
        ("isle of man",   "Isle of Man"),
        ("london",        "London"),
        ("lincolnshire",  "Lincolnshire"),
        ("durham",        "County Durham"),
        ("northumberland","Northumberland"),
        ("cumbria",       "Cumbria"),
        ("lake district", "Cumbria"),
        ("dartmoor",      "Devon"),
        ("exmoor",        "Somerset"),
        ("somerset",      "Somerset"),
        ("kent",          "Kent"),
        ("sussex",        "Sussex"),
        ("dorset",        "Dorset"),
        ("wiltshire",     "Wiltshire"),
    ]
    for keyword, region in regions:
        if keyword in text:
            return region
    return "Britain"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cleanup — apply_cleanup, REMOVE_ENTRIES, FORCE_CATEGORY etc.
# ---------------------------------------------------------------------------

CATEGORY_REMAP = {
    "ancient_site": "location",
    "ritual":       "location",
    "norse":        "fairy",
}

VALID_CATEGORIES = {
    "beast", "ghost", "fairy", "water", "dragon", "witch",
    "deity", "giant", "location", "hero", "pirate"
}

REMOVE_ENTRIES = {
    "Cardiff University", "English Folk Dance and Song Society",
    "School of Scottish Studies", "SM UB-85",
    "Battle of Britain Memorial, Capel-le-Ferne", "Bulford Kiwi",
    "Barns of Ayr", "Lancashire Witches Walk",
    "River Tamar", "Loch Linnhe", "Black Rock Gorge",
    "Kitterland", "Kirriemuir", "Whitehawk", "Witchknowe Park",
    "Morrison\'s Haven", "Smeaton House", "Gatton Park",
    "Osmington White Horse", "Folkestone White Horse",
    "Watlington White Mark", "Whiteleaf Cross", "Lenham Cross",
    "Spong Hill", "Fintan\'s Grave", "Lia Fáil", "Mag Lena",
    "Latoon Fairy Bush", "Latoon fairy bush",
    "Four Ashes, Buckinghamshire", "Harrow on the Hill", "Kirkharle",
    "Thundersley", "Thursley", "Wednesbury", "Weedon Lois", "Weeley",
    "Wing, Buckinghamshire", "Woodnesborough", "Wye, Kent", "Lenham",
    "Fovant Badges", "Shoreham Memorial Cross", "Porthchapel Beach",
    "St Anthony-in-Meneage", "White Lion Inn, Stratford-upon-Avon",
    "Kirkcudbright Tolbooth", "Keith Marischal", "Innerwick Castle",
    "Canewdon", "Crook of Devon", "Museum of Witchcraft and Magic",
    "Overtoun Bridge",
    "Boulogne-sur-Mer", "Byland Abbey", "Cambridge University Press",
    "England", "English Channel",
    "Enfield poltergeist", "The Giant of Cerne Abbas",
    "The Long Man of Wilmington", "Witches\' Well, Edinburgh",
    "Fairy Bridge (Isle of Man)", "Nine Maidens stone row",
    "Stanton Drew stone circles", "Whetstones",
    "The Giant\'s Causeway",
    "Beinn a\' Bheithir",
    # Wikipedia category spillover: geography, museums and ordinary sites
    # without a stated folklore, pagan-tradition or megalithic connection.
    "Connacht", "Galway", "Leinster", "Munster", "River Boyne",
    "Carn, County Fermanagh", "National Leprechaun Museum",
    "Lough Scur", "Reask", "St Davids Cathedral", "Sutton Hoo",
    "Mordiford Dragon",
    "St Leonard's Forest Dragons",  # superseded by our seed "Dragon of St Leonard's Forest"
}

FORCE_CATEGORY = {
    "Gogmagog": "giant", "Fingal": "giant", "Rhitta Gawr": "giant",
    "Bran the Blessed": "giant", "Cerne Abbas Giant": "giant",
    "Giant\'s Causeway": "giant", "Plynlimon": "giant",
    "Gog and Magog": "giant", "Penhill Giant": "giant",
    "Balor of the Evil Eye": "giant",
    "Lancelot": "hero", "Gawain": "hero", "Beowulf": "hero",
    "The Green Knight": "hero", "Corineus": "hero",
    "Cú Chulainn": "hero", "Fionn mac Cumhaill": "hero",
    "Boudicca": "hero", "Wayland the Smith": "hero",
    "Dunstan and the Devil": "hero", "Dick Turpin": "hero",
    "Mabon ap Modron": "deity", "Blodeuwedd": "deity",
    "Gwyn ap Nudd": "deity", "Merlin": "deity",
    "Hafren": "deity", "Gwy": "deity", "Rheidol": "deity",
    "Elder Mother": "deity", "The Dagda": "deity",
    "Queen Medb": "deity", "Cailleach Bhéara": "deity",
    "Tuatha Dé Danann": "deity",
    "Helen Duncan": "witch", "Mother Ludlam": "witch",
    "Children of Lir": "water", "Sea Mither": "water",
    "Teran": "water",
    "Merlin": "hero",
    "Redcap": "fairy", "The Black Dog of Newgate": "ghost",
    "Cock Lane ghost": "ghost", "Bean Nighe": "ghost",
    "Lantern Man": "ghost", "Banshee": "ghost", "Wights": "ghost",
    "Nanny Rutt": "water", "Glaistig": "fairy",
    "Blue Men of the Minch": "water", "Salmon of Knowledge": "water",
    "Maeshowe Runes": "location", "Orkneyinga Saga": "hero",
    "Beltane Fire Festival": "location",
    "Hobby Horse of Padstow": "location",
    "Mari Lwyd": "location", "Up Helly Aa": "location",
    "Cheetham Close": "location", "Craddock Moor stone circle": "location",
    "Bryn Cader Faner": "location", "Bryn Gwyn stones": "location",
    "Nine Maidens Stone Row": "location",
    "Stanton Drew Stone Circles": "location",
    "Whetstones (stone circle)": "location",
    "St Trinian\'s Church": "location",
    "Cantre\'r Gwaelod": "location", "Battle of Barry": "location",
    "Lochmaben Stone": "location", "Towednack": "location",
    "Caer Bran": "location", "Zennor": "location",
    "Newgrange": "location", "Hill of Tara": "location",
    "Croagh Patrick": "location", "Knocknarea": "location",
    "Camelot": "location", "Avalon": "location",
    "Finn McCools Fingers": "location", "Navan Fort": "location",
    "Rathcroghan": "location", "Blarney Stone": "location",
    "Giant\'s Causeway": "location", "Granny Kempock Stone": "location",
    "Witches\' Well": "location",
    "Dragon Hill, Uffington": "location",
    "Trow": "fairy", "Pooka": "fairy", "Aos Sí": "fairy",
    "Tylwyth Teg": "fairy", "Seelie Court": "fairy",
    "Unseelie Court": "fairy", "Boggarts": "fairy",
    "Pixie": "fairy", "Yallery Brown": "fairy",
    "Brown Man of the Muirs": "fairy", "Gooseberry Wife": "fairy",
    "Hyter Sprite": "fairy",
    "The Green Man": "fairy",
    "Loftus Hall": "ghost",
    "Filey Dragon": "dragon", "Gurt Worm": "dragon",
    "Mordiford Dragon": "dragon",
    "Black Annis": "beast", "Wisht Hounds": "beast",
    "Renwick Cockatrice": "beast", "Fad Felen": "beast",
    "Hartlepool Monkey": "beast",
    "Grace O\'Malley": "pirate", "Blackbeard": "pirate",
    "Anne Bonny": "pirate", "Mary Read": "pirate",
    "Black Bart Roberts": "pirate", "Calico Jack": "pirate",
    "Henry Every": "pirate", "William Kidd": "pirate",
    "Davy Jones": "pirate",
}

DISPLAY_NAME_SUFFIX_RE = re.compile(
    r"\s+\([^)]*(?:privateer|tradition|stone circle|legend|folklore)[^)]*\)$",
    re.IGNORECASE,
)

REGION_OVERRIDES = {
    "Ashleypark Burial Mound": "Ashleypark, County Tipperary",
    "Battle of Barry": "Barry, Angus, Scotland",
    "Beenalaght": "Coachford, County Cork",
    "Behy court tomb": "Belderrig, County Mayo",
    "Blarney Stone": "Blarney Castle, County Cork",
    "Breeny More Stone Circle": "Breeny More, County Cork",
    "Bryn Cader Faner": "Ardudwy, Gwynedd, Wales",
    "Bryn Gwyn stones": "Brynsiencyn, Anglesey, Wales",
    "Brú na Bóinne": "Boyne Valley, County Meath",
    "Cantre'r Gwaelod": "Cardigan Bay, Wales",
    "Caerleon": "Caerleon, Newport, Wales",
    "Carricknagat Megalithic Tombs": "Carricknagat, County Sligo",
    "Carrigagulla": "Carrigagulla, County Cork",
    "Carrigaphooca Stone Circle": "Carrigaphooca, County Cork",
    "Carrowmore": "Carrowmore, County Sligo",
    "Carrownlisheen Wedge Tomb": "Carrownlisheen, County Clare",
    "Clodagh Standing Stones": "Clodagh, County Cork",
    "Cloghanmore": "Glencolmcille, County Donegal",
    "Coolcoulaghta Standing Stones": "Coolcoulaghta, County Cork",
    "Craigs Dolmen": "Craigs, County Antrim",
    "Dolmen of the Four Maols": "Ballina, County Mayo",
    "Eightercua": "Waterville, County Kerry",
    "Farranahineeny Stone Row": "Farranahineeny, County Kerry",
    "Fat Lips": "Jedburgh Castle Jail, Scottish Borders",
    "Finn McCools Fingers": "Shantemon Mountain, County Cavan",
    "Giant's Causeway": "Bushmills, County Antrim",
    "Glantane East": "Glantane, County Cork",
    "Gulf of Corryvreckan": "Between Jura and Scarba, Argyll",
    "Heapstown Cairn": "Heapstown, County Sligo",
    "Henderson Stone": "Ardgour, Lochaber",
    "Knocknakilla": "Knocknakilla, County Cork",
    "Labbacallee wedge tomb": "Glanworth, County Cork",
    "Listoghil": "Carrowmore, County Sligo",
    "Llyn y Fan Fach": "Bannau Brycheiniog, Carmarthenshire",
    "Lochmaben Stone": "Gretna, Dumfries and Galloway",
    "Loftus Hall": "Hook Peninsula, County Wexford",
    "Meehambee Dolmen": "Meehambee, County Roscommon",
    "Merlin's Oak": "Carmarthen, Wales",
    "Miosgán Meadhbha": "Knocknarea, County Sligo",
    "Moel Tŷ Uchaf": "Llandrillo, Denbighshire, Wales",
    "Mount Venus": "Rathfarnham, County Dublin",
    "Mullyash Kerbed Cairn": "Mullyash, County Armagh",
    "Navan Fort": "Emain Macha, County Armagh",
    "Newgrange cursus": "Newgrange, County Meath",
    "Rathcoran": "Baltinglass, County Wicklow",
    "Rathcroghan": "Rathcroghan, County Roscommon",
    "Salmon of Knowledge": "River Boyne, County Meath",
    "Thornton Road poltergeist claim": "Ward End, Birmingham",
    "Timoney Stones": "Timoney, County Tipperary",
    "Townleyhall passage grave": "Townleyhall, County Louth",
    "Turoe Stone": "Bullaun, County Galway",
    "Waun Mawn": "Preseli Hills, Pembrokeshire, Wales",
    "Whetstones": "Welshpool, Powys, Wales",
    "Yester Castle": "Gifford, East Lothian",
    "Ystwyth": "Ceredigion, Wales",
}

COORD_OVERRIDES = {
    # Shoreline anchor for the submerged kingdom: Borth Beach's exposed
    # forest is explicitly associated with the Cantre'r Gwaelod tradition.
    "Cantre'r Gwaelod": (52.488, -4.052),
}


def _normalise(name: str) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", name.lower())
    n = re.sub(r"[^a-z0-9 ]", "", n)
    for prefix in ("the ", "a ", "an "):
        if n.startswith(prefix):
            n = n[len(prefix):]
    return n.strip()


def is_duplicate(name: str, existing_names: set) -> bool:
    norm = _normalise(name)
    for e in existing_names:
        en = _normalise(e)
        if norm == en:
            return True
        if len(norm) >= 5 and len(en) >= 5 and (norm in en or en in norm):
            return True
    return False


# A few seed names are genuine duplicates of an existing canonical entry
# (e.g. "Cerne Abbas Giant"). These stay on the blocklist even though they
# may appear in seeds, so we never get a double pin on the map.
BLOCKLIST_KEEP = {
    "The Giant of Cerne Abbas",
    "St Leonard's Forest Dragons",
    "Mordiford Dragon",
}


def apply_cleanup(legends: dict) -> dict:
    removed = fixed = renamed = 0
    # Hand-curated seeds always take priority and must never be silently
    # dropped by the junk blocklist. Subtract seed names from the effective
    # remove set (except the explicit BLOCKLIST_KEEP duplicates above) so a
    # deliberately-curated entry can never be killed by a stale REMOVE_ENTRIES
    # line — this previously lost ~20 real entries (Sutton Hoo, Overtoun
    # Bridge, the white horses, etc.).
    seed_names = {l["name"] for l in SEED_LEGENDS}
    effective_remove = REMOVE_ENTRIES - (seed_names - BLOCKLIST_KEEP)
    for name in list(legends.keys()):
        if name in effective_remove:
            del legends[name]
            removed += 1
            continue
        display_name = DISPLAY_NAME_SUFFIX_RE.sub("", name)
        if display_name != name:
            leg = legends.pop(name)
            leg["name"] = display_name
            legends[display_name] = leg
            renamed += 1
    for leg in legends.values():
        original = leg["category"]
        if leg["name"] in FORCE_CATEGORY:
            leg["category"] = FORCE_CATEGORY[leg["name"]]
        if leg["name"] in REGION_OVERRIDES:
            leg["region"] = REGION_OVERRIDES[leg["name"]]
        if leg["name"] in COORD_OVERRIDES:
            leg["lat"], leg["lng"] = COORD_OVERRIDES[leg["name"]]
        if leg["category"] in CATEGORY_REMAP:
            leg["category"] = CATEGORY_REMAP[leg["category"]]
        if leg["category"] not in VALID_CATEGORIES:
            leg["category"] = "beast"
        if leg["category"] != original:
            fixed += 1
    print(f"      Cleanup: removed {removed}, renamed {renamed}, fixed {fixed} categories")
    return legends


# ---------------------------------------------------------------------------
# Historic Environment Scotland — INSPIRE WFS
# No API key required. Replaces the defunct Canmore API.
# Endpoint: inspire.hes.scot (INSPIRE-compliant WFS, GeoJSON output)
# Covers: Scheduled Monuments, Listed Buildings, Protected Wrecks, Gardens
# ---------------------------------------------------------------------------

# HES ArcGIS REST query endpoints — one URL per layer type
# Each uses the ArcGIS FeatureServer/MapServer REST API (not WFS typenames)
# outputFormat=geojson, no key required
HES_LAYERS = {
    # (query_url, category)
    "Scheduled Monuments": (
        "https://inspire.hes.scot/arcgis/rest/services/HES/Scheduled_Monuments/MapServer/0/query",
        "location"
    ),
    "Listed Buildings": (
        "https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/0/query",
        "location"
    ),
    "Historic Marine Protected Areas": (
        "https://inspire.hes.scot/arcgis/rest/services/HES/Historic_Marine_Protected_Areas/MapServer/0/query",
        "pirate"
    ),
    "Gardens and Landscapes": (
        "https://inspire.hes.scot/arcgis/rest/services/HES/Gardens_and_Designed_Landscapes/MapServer/0/query",
        "location"
    ),
}

# Keywords to filter by — only include sites whose name/description
# suggests folklore, mythology or historical legend relevance
HES_FOLKLORE_TERMS = [
    "stone", "standing", "circle", "cairn", "fort", "broch", "dun",
    "henge", "barrow", "tumulus", "cup", "carved", "cross", "well",
    "castle", "tower", "chapel", "loch", "cave", "crannog",
    "souterrain", "earth", "hill", "burial", "cist", "dolmen",
    "ghost", "haunted", "legend", "witch", "fairy", "monster",
    "battle", "sacred", "holy", "ancient", "prehistoric",
    "wreck", "smuggl", "pirat",
]

PIRATE_RELATED_TERMS = [
    "pirat", "privateer", "buccaneer", "corsair", "smuggl",
    "wrecking", "wrecker", "treasure",
]

HERITAGE_LORE_PATTERNS = [
    r"\bdevil(?:'s|s)?\b", r"\bfair(?:y|ies)\b", r"\bfaerie\b",
    r"\bgiant(?:'s|s')?\b", r"\bghost\b", r"\bhaunted\b",
    r"\bwitch(?:es|craft|y)?\b", r"\bdragon\b", r"\bmermaid\b",
    r"\bmonster\b", r"\blegend(?:ary)?\b", r"\bfolklore\b",
    r"\bmyth(?:ic|ical|ological)?\b", r"\bholy well\b",
    r"\bsacred\b", r"\britual\b", r"\btreasure\b", r"\bsmuggl\w*\b",
    r"\bpirat\w*\b", r"\bprivateer\w*\b", r"\bwrecker\w*\b",
]


def _he_term_relevant(name: str, desc: str = "") -> bool:
    """Return True only when a heritage record explicitly signals lore."""
    text = (name + " " + desc).lower()
    return any(re.search(pattern, text) for pattern in HERITAGE_LORE_PATTERNS)

def _pirate_term_relevant(name: str, desc: str = "") -> bool:
    """Exclude ordinary wrecks unless the record signals pirate-related lore."""
    text = (name + " " + desc).lower()
    return any(t in text for t in PIRATE_RELATED_TERMS)


def fetch_hes_wfs(verbose: bool = False) -> list:
    """
    Query Historic Environment Scotland via ArcGIS REST API.
    Replaces the defunct Canmore API. No key required.
    Covers Scotland: Scheduled Monuments, Listed Buildings,
    Protected Wrecks, and Gardens/Designed Landscapes.
    """
    results  = []
    seen_ids = set()

    for layer_name, (query_url, category) in HES_LAYERS.items():
        if verbose:
            print(f"    [HES] Fetching: {layer_name}")

        # ArcGIS REST query params
        params = {
            "where":         "1=1",           # all records
            "outFields":     "*",             # all attributes
            "f":             "geojson",       # GeoJSON output
            "outSR":         4326,
            "resultOffset":  0,
            "resultRecordCount": 1000,
            "geometryType":  "esriGeometryEnvelope",
            # Scotland bounding box in WGS84
            "geometry":      "-8.0,54.5,-0.5,61.5",
            "inSR":          4326,
            "spatialRel":    "esriSpatialRelIntersects",
            "returnGeometry": "true",
            "returnCentroid": "true",
        }

        page = 0
        while True:
            params["resultOffset"] = page * 1000
            try:
                r = requests.get(
                    query_url, params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=60
                )
                r.raise_for_status()
                data     = r.json()
                if data.get("error"):
                    raise RuntimeError(data["error"])
                features = data.get("features", [])

                if not features:
                    break

                for feat in features:
                    props   = feat.get("properties", {})
                    site_id = (props.get("ENT_REF") or props.get("DES_REF") or
                               props.get("FID") or props.get("OBJECTID"))
                    unique_id = f"{layer_name}:{site_id}"
                    if not site_id or unique_id in seen_ids:
                        continue
                    seen_ids.add(unique_id)

                    # Get centroid — ArcGIS polygons need manual centroid calc
                    geom = feat.get("geometry", {})
                    lat = lng = None

                    if geom:
                        # Point geometry
                        if geom.get("x") is not None:
                            lng, lat = float(geom["x"]), float(geom["y"])
                        elif geom.get("type") == "Point":
                            coords = geom.get("coordinates", [])
                            if len(coords) >= 2:
                                lng, lat = map(float, coords[:2])
                        # Polygon with rings (ArcGIS format)
                        elif "rings" in geom and geom["rings"]:
                            ring = geom["rings"][0]
                            if ring:
                                lng = sum(c[0] for c in ring) / len(ring)
                                lat = sum(c[1] for c in ring) / len(ring)
                        # GeoJSON Polygon
                        elif geom.get("type") == "Polygon":
                            coords = geom.get("coordinates", [[]])[0]
                            if coords:
                                lng = sum(c[0] for c in coords) / len(coords)
                                lat = sum(c[1] for c in coords) / len(coords)
                        elif geom.get("type") == "MultiPolygon":
                            coords = geom.get("coordinates", [[[]]])[0][0]
                            if coords:
                                lng = sum(c[0] for c in coords) / len(coords)
                                lat = sum(c[1] for c in coords) / len(coords)

                    if lat is None or lng is None:
                        continue
                    if not is_in_uk(float(lat), float(lng)):
                        continue

                    name = (props.get("ENT_TITLE") or props.get("DES_TITLE") or
                            props.get("NAME") or "").strip()
                    if not name:
                        continue

                    desc = " ".join(str(value).strip() for value in (
                        props.get("DES_TYPE"), props.get("CATEGORY"),
                        props.get("GROUPCAT"), props.get("GROUP_CATE"),
                        props.get("PARISH"), props.get("PARBUR"),
                    ) if value)

                    # Ordinary protected wrecks are not pirate lore.
                    if category == "pirate" and not _pirate_term_relevant(name, desc):
                        continue
                    if category != "pirate" and not _he_term_relevant(name, desc):
                        continue

                    # Build summary
                    period = (props.get("DES_TYPE") or "").strip()
                    if desc:
                        summary = desc[:450]
                        if len(desc) > 450:
                            cut = summary.rfind(". ")
                            summary = summary[:cut + 1] if cut > 150 else summary[:447] + "..."
                    else:
                        parts   = [p for p in [period] if p]
                        summary = f"{name} — {', '.join(parts)}." if parts else                                   f"{name} — a protected heritage site in Scotland."

                    source = (props.get("LINK") or
                              f"https://portal.historicenvironment.scot/designation/{props.get('DES_REF', site_id)}")
                    region = infer_region(name, summary)

                    results.append({
                        "name":     name,
                        "lat":      round(float(lat), 4),
                        "lng":      round(float(lng), 4),
                        "category": category,
                        "region":   region,
                        "summary":  summary,
                        "source":   source,
                    })

                # ArcGIS returns up to 1000 per page — check if more exist
                exceeded = data.get("exceededTransferLimit", False)
                if not exceeded or len(features) < 1000:
                    break
                page += 1
                time.sleep(RATE_LIMIT)

            except requests.exceptions.Timeout:
                print(f"    [HES] Timeout on {layer_name} — skipping")
                break
            except (requests.exceptions.RequestException, RuntimeError) as e:
                print(f"    [HES] Error on {layer_name}: {e}")
                break

        if verbose:
            print(f"    [HES] {layer_name}: done ({len(results)} cumulative)")
        time.sleep(RATE_LIMIT)

    print(f"    [HES] {len(results)} total Scottish heritage sites fetched")
    return results

# ---------------------------------------------------------------------------
# Historic England — Heritage Gateway / National Heritage List
# No API key required. Covers England and Wales.
# ---------------------------------------------------------------------------

HE_SEARCH_URL = "https://services.historicengland.org.uk/NMRDataDownload/GeoSearch.aspx"

HE_TYPE_MAP = {
    "Scheduled Monument":          "location",
    "Listed Building":             "ghost",
    "Registered Park and Garden":  "location",
    "Protected Wreck":             "pirate",
    "World Heritage Site":         "location",
}

HE_FOLKLORE_TERMS = [
    "legend", "folklore", "tradition", "myth", "fairy", "ghost",
    "haunted", "witch", "sacred", "holy well", "monster", "giant",
    "smuggler", "pirate", "wreck", "treasure", "standing stone",
    "stone circle", "barrow", "hillfort", "henge", "cursus",
    "earthwork", "cairn", "broch", "dolmen", "menhir", "tumulus",
]


# ---------------------------------------------------------------------------
# Historic England — National Heritage List for England (NHLE) ArcGIS REST
# Same pattern as HES. No key required.
# Spatial reference 27700 (British National Grid) → request outSR=4326
# Layers: 0=Listed Buildings, 6=Scheduled Monuments, 7=Parks & Gardens,
#         8=Battlefields, 9=Protected Wreck Sites, 10=World Heritage Sites
# ---------------------------------------------------------------------------

NHLE_BASE = "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer"

NHLE_LAYERS = {
    "Scheduled Monuments":    (f"{NHLE_BASE}/6/query",  "location"),
    "Protected Wreck Sites":  (f"{NHLE_BASE}/9/query",  "pirate"),
    "Parks and Gardens":      (f"{NHLE_BASE}/7/query",  "location"),
    "Battlefields":           (f"{NHLE_BASE}/8/query",  "location"),
    "World Heritage Sites":   (f"{NHLE_BASE}/10/query", "location"),
}

# Keywords to filter by — only sites whose name suggests folklore relevance
NHLE_FOLKLORE_TERMS = [
    "stone", "standing", "circle", "cairn", "fort", "castle", "tower",
    "henge", "barrow", "tumulus", "cross", "well", "burial", "dolmen",
    "earthwork", "hill", "mound", "ditch", "sacred", "holy", "ancient",
    "battle", "camp", "wreck", "smuggl", "pirat", "chapel", "priory",
    "abbey", "temple", "cursus", "enclosure", "ring", "long",
]

def _nhle_relevant(name: str) -> bool:
    return _he_term_relevant(name)

def fetch_historic_england(verbose: bool = False) -> list:
    """
    Query Historic England NHLE via ArcGIS REST API.
    Requests outSR=4326 so coordinates come back in WGS84 — no conversion needed.
    No API key required.
    """
    results  = []
    seen_ids = set()

    for layer_name, (query_url, category) in NHLE_LAYERS.items():
        if verbose:
            print(f"    [Historic England] Fetching: {layer_name}")

        page = 0
        while True:
            params = {
                "where":              "1=1",
                "outFields":          "*",
                "f":                  "json",          # JSON output
                "outSR":              4326,             # reproject to WGS84 server-side
                "returnGeometry":     "true",
                "returnCentroid":     "true",
                "resultOffset":       page * 1000,
                "resultRecordCount":  1000,
                "geometryType":       "esriGeometryEnvelope",
                # England + Wales bounding box in WGS84
                "geometry":           "-5.7,49.9,1.8,55.8",
                "inSR":              4326,
                "spatialRel":        "esriSpatialRelIntersects",
            }
            try:
                r = requests.get(
                    query_url, params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=60
                )
                r.raise_for_status()
                data     = r.json()
                if data.get("error"):
                    raise RuntimeError(data["error"])
                features = data.get("features", [])

                if not features:
                    break

                for feat in features:
                    attrs   = feat.get("attributes", {})
                    site_id = (attrs.get("ListEntry") or
                               attrs.get("OBJECTID") or "")
                    if not site_id or str(site_id) in seen_ids:
                        continue
                    seen_ids.add(str(site_id))

                    # Coordinates — prefer centroid, fall back to geometry
                    geom = feat.get("geometry", {})
                    lat = lng = None

                    if geom:
                        if geom.get("x") is not None:
                            lng, lat = float(geom["x"]), float(geom["y"])
                        elif "rings" in geom and geom["rings"]:
                            ring = geom["rings"][0]
                            if ring:
                                lng = sum(c[0] for c in ring) / len(ring)
                                lat = sum(c[1] for c in ring) / len(ring)
                        elif geom.get("type") == "Polygon":
                            coords = geom.get("coordinates", [[]])[0]
                            if coords:
                                lng = sum(c[0] for c in coords) / len(coords)
                                lat = sum(c[1] for c in coords) / len(coords)

                    if lat is None or lng is None:
                        continue
                    if not is_in_uk(float(lat), float(lng)):
                        continue

                    name = (attrs.get("Name") or "").strip()
                    if not name:
                        continue

                    desc   = ""
                    period = ""
                    grade  = (attrs.get("Grade") or "").strip()

                    # Ordinary protected wrecks are not pirate lore.
                    if category == "pirate" and not _pirate_term_relevant(name, desc):
                        continue
                    if category != "pirate" and not _nhle_relevant(name):
                        continue

                    if desc:
                        summary = desc[:450]
                        if len(desc) > 450:
                            cut = summary.rfind(". ")
                            summary = summary[:cut + 1] if cut > 150 else summary[:447] + "..."
                    else:
                        parts = [p for p in [period, grade] if p]
                        summary = f"{name} — {', '.join(parts)}." if parts else                                   f"{name} — a scheduled heritage site in England."

                    entry_no = attrs.get("ListEntry", "")
                    source   = (attrs.get("hyperlink") or
                                (f"https://historicengland.org.uk/listing/the-list/list-entry/{entry_no}"
                                 if entry_no else "https://historicengland.org.uk"))
                    region   = infer_region(name, summary)

                    results.append({
                        "name":     name,
                        "lat":      round(float(lat), 4),
                        "lng":      round(float(lng), 4),
                        "category": category,
                        "region":   region,
                        "summary":  summary,
                        "source":   source,
                    })

                exceeded = data.get("exceededTransferLimit", False)
                if not exceeded or len(features) < 1000:
                    break
                page += 1
                time.sleep(RATE_LIMIT)

            except requests.exceptions.Timeout:
                print(f"    [Historic England] Timeout on {layer_name} — skipping")
                break
            except (requests.exceptions.RequestException, RuntimeError) as e:
                print(f"    [Historic England] Error on {layer_name}: {e}")
                break

        if verbose:
            print(f"    [Historic England] {layer_name}: done ({len(results)} cumulative)")
        time.sleep(RATE_LIMIT)

    print(f"    [Historic England] {len(results)} sites fetched")
    return results


# ---------------------------------------------------------------------------
# DBpedia SPARQL — structured Wikipedia data, better folklore coverage
# than raw Wikipedia category pulls. Free, no key required.
# Endpoint: https://dbpedia.org/sparql
# ---------------------------------------------------------------------------

DBPEDIA_SPARQL = "https://dbpedia.org/sparql"

# DBpedia categories to query — focused on British Isles folklore
DBPEDIA_CATEGORIES = [
    # Creatures & beings
    ("English_legendary_creatures",      "beast"),
    ("Scottish_legendary_creatures",     "beast"),
    ("Welsh_legendary_creatures",        "beast"),
    ("Irish_legendary_creatures",        "beast"),
    ("British_legendary_creatures",      "beast"),
    ("Lake_monsters",                    "water"),
    ("Sea_monsters",                     "water"),
    ("Water_spirits",                    "water"),
    ("Selkies",                          "water"),
    ("Kelpies",                          "water"),
    ("Mermaids",                         "water"),
    ("Fairies",                          "fairy"),
    ("Irish_fairies",                    "fairy"),
    ("Scottish_fairies",                 "fairy"),
    ("Goblins",                          "fairy"),
    ("Brownies_(mythology)",             "fairy"),
    ("Ghosts",                           "ghost"),
    ("English_ghosts",                   "ghost"),
    ("Scottish_ghosts",                  "ghost"),
    ("Irish_ghosts",                     "ghost"),
    ("British_witchcraft",               "witch"),
    ("Scottish_witchcraft",              "witch"),
    ("Witches",                          "witch"),
    ("Dragons_in_mythology",             "dragon"),
    ("Welsh_dragons",                    "dragon"),
    ("Giants_in_mythology",              "giant"),
    # Deities & heroes
    ("Celtic_gods",                      "deity"),
    ("Irish_gods",                       "deity"),
    ("Welsh_gods",                       "deity"),
    ("Tuatha_Dé_Danann",                 "deity"),
    ("Arthurian_characters",             "deity"),
    ("Characters_in_Irish_mythology",    "deity"),
    ("Ulster_Cycle",                     "deity"),
    ("Fenian_Cycle",                     "deity"),
    # Locations
    ("Sacred_sites_in_the_United_Kingdom", "location"),
    ("Haunted_locations_in_England",     "location"),
    ("Haunted_locations_in_Scotland",    "location"),
    ("Haunted_locations_in_Ireland",     "location"),
    ("Stone_circles_in_the_British_Isles", "location"),
    ("Megalithic_monuments_in_Scotland", "location"),
    ("Megalithic_monuments_in_Ireland",  "location"),
    # Pirates
    ("English_pirates",                  "pirate"),
    ("Scottish_pirates",                 "pirate"),
    ("Irish_pirates",                    "pirate"),
    ("Welsh_pirates",                    "pirate"),
    ("Privateers",                       "pirate"),
    ("British_pirates",                  "pirate"),
    ("Smuggling_in_the_United_Kingdom",  "pirate"),
    ("Maritime_folklore",                "water"),
]


def fetch_dbpedia(verbose: bool = False) -> list:
    """
    Query DBpedia SPARQL for British Isles folklore entities with coordinates.
    DBpedia extracts structured data from Wikipedia including geo coordinates,
    abstracts and category memberships — more reliable than raw Wikipedia API.
    No key required.
    """
    results   = []
    seen_uris = set()

    # Query without geo filter — most folklore entities lack DBpedia coords.
    # We get names + abstracts, then use Wikipedia geodata API for coords.
    query_template = """
PREFIX dbo:  <http://dbpedia.org/ontology/>
PREFIX dbc:  <http://dbpedia.org/resource/Category:>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?entity ?name ?abstract WHERE {{
  ?entity dct:subject dbc:{category} .
  ?entity rdfs:label ?name .
  ?entity dbo:abstract ?abstract .
  FILTER (lang(?name) = 'en')
  FILTER (lang(?abstract) = 'en')
}}
LIMIT 200
"""

    for category, cat_type in DBPEDIA_CATEGORIES:
        if verbose:
            print(f"    [DBpedia] Querying: {category}")

        query = query_template.format(category=category)
        try:
            r = requests.get(
                DBPEDIA_SPARQL,
                params={
                    "query":  query,
                    "format": "application/sparql-results+json",
                },
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept":     "application/sparql-results+json",
                },
                timeout=30
            )
            r.raise_for_status()
            data    = r.json()
            results_raw = data.get("results", {}).get("bindings", [])

            if verbose:
                print(f"    [DBpedia]   {len(results_raw)} results")

            # Collect names + abstracts from this category
            candidates = {}
            for row in results_raw:
                uri  = row.get("entity", {}).get("value", "")
                if not uri or uri in seen_uris:
                    continue
                name     = row.get("name", {}).get("value", "").strip()
                abstract = row.get("abstract", {}).get("value", "").strip()
                if not name:
                    continue
                wiki_title = uri.replace("http://dbpedia.org/resource/", "").replace("_", " ")
                candidates[wiki_title] = (name, abstract, uri, cat_type)

            if not candidates:
                continue

            # Fetch coordinates via Wikipedia geodata API (batch)
            titles_list = list(candidates.keys())
            if verbose:
                print(f"    [DBpedia]   {len(titles_list)} candidates, fetching coords...")
            geodata = get_article_geodata(titles_list, verbose)
            if cat_type == "pirate":
                missing_titles = [
                    title for title in titles_list if title not in geodata
                ]
                geodata.update(
                    get_pirate_birthplace_geodata(missing_titles, verbose)
                )

            for wiki_title, (lat, lng) in geodata.items():
                if not is_in_uk(lat, lng):
                    continue
                if wiki_title not in candidates:
                    continue
                name, abstract, uri, cat = candidates[wiki_title]
                seen_uris.add(uri)

                summary = abstract
                if len(summary) > 450:
                    cut = summary[:450].rfind(". ")
                    summary = summary[:cut + 1] if cut > 150 else summary[:447] + "..."
                if cat == "pirate" and wiki_title not in PIRATE_FOLKLORE_TITLES:
                    continue

                source = f"https://en.wikipedia.org/wiki/{requests.utils.quote(wiki_title.replace(chr(32), chr(95)))}"
                region = infer_region(name, summary)

                results.append({
                    "name":     name,
                    "lat":      round(lat, 4),
                    "lng":      round(lng, 4),
                    "category": cat,
                    "region":   region,
                    "summary":  summary,
                    "source":   source,
                })

            time.sleep(RATE_LIMIT * 2)  # be kind to the public endpoint

        except requests.exceptions.Timeout:
            print(f"    [DBpedia] Timeout on {category} — skipping")
        except requests.exceptions.RequestException as e:
            print(f"    [DBpedia] Error on {category}: {e}")

    print(f"    [DBpedia] {len(results)} entities fetched")
    return results


# ---------------------------------------------------------------------------
# Supabase write helper
# ---------------------------------------------------------------------------

import os as _os


def _clean_env_value(name: str) -> str:
    """Accept values set with shell syntax that accidentally preserves quotes."""
    return _os.getenv(name, "").strip().strip("\"'")


SUPABASE_URL         = _clean_env_value("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _clean_env_value("SUPABASE_SERVICE_KEY")


def _supabase_headers():
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal,resolution=merge-duplicates",
    }


def _supabase_url(path: str = "") -> str:
    base = f"{SUPABASE_URL.rstrip('/')}/rest/v1/legends"
    return f"{base}?{path}" if path else base


def _supabase_request(method: str, url: str, **kwargs):
    response = requests.request(
        method, url, headers=_supabase_headers(), timeout=30, **kwargs
    )
    if not response.ok:
        detail = response.text[:300].strip()
        raise RuntimeError(
            f"Supabase {method} failed: HTTP {response.status_code}"
            + (f" ({detail})" if detail else "")
        )
    return response


def _supabase_names() -> set:
    response = _supabase_request("GET", _supabase_url("select=name&limit=10000"))
    return {row["name"] for row in response.json()}


def _delete_stale_supabase_rows(stale_names: set) -> int:
    if not stale_names:
        return 0
    quoted_names = ",".join(
        f'"{name.replace(chr(34), chr(34) * 2)}"' for name in sorted(stale_names)
    )
    encoded_names = requests.utils.quote(quoted_names, safe='(),"')
    _supabase_request(
        "DELETE",
        _supabase_url(f"name=in.({encoded_names})"),
    )
    return len(stale_names)


def write_to_supabase(
    legends: dict, verbose: bool = False, prune: bool = False
) -> None:
    """Upsert legends and optionally delete remote rows absent from local JSON."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
    url   = _supabase_url("on_conflict=name")
    rows  = list(legends.values())
    total = len(rows)
    batch_size = 50
    success = 0
    print(f"      Syncing {total} legends to Supabase ...")
    for i in range(0, total, batch_size):
        batch = [{
            "name":       r["name"],
            "lat":        r["lat"],
            "lng":        r["lng"],
            "category":   r.get("category", "beast"),
            "region":     r.get("region", "Britain"),
            "summary":    r.get("summary", ""),
            "source":     r.get("source", ""),
            "detail":     r.get("detail") or None,
            "tags":       r.get("tags") or [],
            "date_added": r.get("date_added") or None,
            "origin_date":         r.get("origin_date") or None,
            "earliest_record":     r.get("earliest_record") or None,
            "period":              r.get("period") or None,
            # Added 2026-08-31, AFTER the add_period_slug migration was applied.
            # Order matters: this line without the column is a 23514 that blocks
            # the whole day's sync.
            "period_slug":         r.get("period_slug") or None,
            "historical_setting":  r.get("historical_setting") or None,
            "cultural_tradition":  r.get("cultural_tradition") or None,
            "origin_type":         r.get("origin_type") or None,
            "dating_confidence":   r.get("dating_confidence") or None,
            "alt_names":           r.get("alt_names") or [],
        } for r in rows[i:i + batch_size]]
        _supabase_request("POST", url, json=batch)
        success += len(batch)
        time.sleep(0.2)
    print(f"      Supabase: {success}/{total} synced")
    if prune:
        stale_names = _supabase_names() - set(legends.keys())
        deleted = _delete_stale_supabase_rows(stale_names)
        print(f"      Supabase: {deleted} stale rows deleted")


def build(limit: int, seed_only: bool, verbose: bool,
          use_hes: bool = False, use_he: bool = False,
          use_dbpedia: bool = False, supabase: bool = False,
          supabase_prune: bool = False,
          output_path: str = "legends.json") -> None:
    print("\n  Folklore Map — legend data pipeline")
    print("  " + "-" * 44)

    # ── Load existing legends.json ─────────────────────────────────────
    import os
    existing = {}
    if os.path.exists("legends.json"):
        try:
            with open("legends.json", encoding="utf-8") as f:
                saved = json.load(f)
            existing = {l["name"]: l for l in saved.get("legends", [])}
            print(f"\n  [0/4] Existing legends.json: {len(existing)} entries preserved")
        except Exception as e:
            print(f"\n  [0/4] Could not read legends.json ({e}) — starting fresh")
    else:
        print(f"\n  [0/4] No existing legends.json — starting fresh")

    # ── Seeds always win ──────────────────────────────────────────────
    legends = dict(existing)
    seed_updated = 0
    for leg in SEED_LEGENDS:
        if leg["name"] not in legends or legends[leg["name"]] != leg:
            if leg["name"] in legends:
                seed_updated += 1
            legends[leg["name"]] = leg
    print(f"\n  [1/4] Seeds: {len(SEED_LEGENDS)} "
          f"({seed_updated} updated, {len(SEED_LEGENDS) - seed_updated} unchanged)")
    legends = apply_cleanup(legends)

    if seed_only:
        print("\n  [2/4] Wikipedia skipped (--seed-only)")
        print("\n  [3/4] External sources skipped (--seed-only)")
    else:
        # ── Wikipedia ─────────────────────────────────────────────────
        print(f"\n  [2/4] Wikipedia: {len(CATEGORIES)} categories, {len(LISTS)} lists ...")
        all_titles = {}
        added = out_of_uk = duplicates = 0

        for cat_name, cat_type in CATEGORIES:
            if verbose:
                print(f"\n    Category: {cat_name}")
            for m in get_category_members(cat_name, limit, verbose):
                if m["title"] not in all_titles:
                    all_titles[m["title"]] = cat_type
            time.sleep(RATE_LIMIT)

        print(f"      Pulling from {len(LISTS)} list articles ...")
        for list_title, list_type in LISTS:
            if verbose:
                print(f"\n    List: {list_title}")
            for m in get_list_members(list_title, verbose):
                if m["title"] not in all_titles:
                    all_titles[m["title"]] = list_type
            time.sleep(RATE_LIMIT)

        print(f"      {len(all_titles)} unique articles")
        geodata = get_article_geodata(list(all_titles.keys()), verbose)
        pirate_titles = [
            title for title, category in all_titles.items()
            if category == "pirate" and title not in geodata
        ]
        geodata.update(get_pirate_birthplace_geodata(pirate_titles, verbose))
        print(f"      {len(geodata)} have coordinates")

        existing_names = set(legends.keys())
        for title, (lat, lng) in geodata.items():
            if not is_in_uk(lat, lng):
                out_of_uk += 1
                continue
            if is_duplicate(title, existing_names):
                duplicates += 1
                continue
            if verbose:
                print(f"    + {title}")
            summary = get_article_summary(title, verbose)
            if not summary:
                summary = f"{title} — a figure from British folklore."
            category = all_titles.get(title, "beast")
            if category == "pirate" and title not in PIRATE_FOLKLORE_TITLES:
                continue
            entry = {
                "name":     title,
                "lat":      round(lat, 4),
                "lng":      round(lng, 4),
                "category": category,
                "region":   infer_region(title, summary),
                "summary":  summary,
                "source":   f"https://en.wikipedia.org/wiki/{requests.utils.quote(title.replace(chr(32), chr(95)))}",
            }
            legends[title] = entry
            existing_names.add(title)
            added += 1
            time.sleep(RATE_LIMIT)

        print(f"\n      Added: {added} | Preserved: {duplicates} | Out of UK: {out_of_uk}")
        legends = apply_cleanup(legends)

        # ── External sources ──────────────────────────────────────────
        print(f"\n  [3/4] External sources ...")

        if use_hes:
            print(f"    Historic Environment Scotland (INSPIRE WFS) ...")
            hes_results    = fetch_hes_wfs(verbose)
            existing_names = set(legends.keys())
            hes_added = 0
            for entry in hes_results:
                if not is_duplicate(entry["name"], existing_names):
                    legends[entry["name"]] = entry
                    existing_names.add(entry["name"])
                    hes_added += 1
            print(f"    HES: {hes_added} new entries added")
        else:
            print(f"    HES WFS: skipped (use --hes to enable)")

        if use_he:
            print(f"    Historic England ...")
            he_results     = fetch_historic_england(verbose)
            existing_names = set(legends.keys())
            he_added = 0
            for entry in he_results:
                if not is_duplicate(entry["name"], existing_names):
                    legends[entry["name"]] = entry
                    existing_names.add(entry["name"])
                    he_added += 1
            print(f"    Historic England: {he_added} new entries added")
        else:
            print(f"    Historic England: skipped (use --historic-england to enable)")

        if use_dbpedia:
            print(f"    DBpedia SPARQL ...")
            dbpedia_results = fetch_dbpedia(verbose)
            existing_names  = set(legends.keys())
            db_added = 0
            for entry in dbpedia_results:
                if not is_duplicate(entry["name"], existing_names):
                    legends[entry["name"]] = entry
                    existing_names.add(entry["name"])
                    db_added += 1
            print(f"    DBpedia: {db_added} new entries added")
        else:
            print(f"    DBpedia: skipped (use --dbpedia to enable)")

        legends = apply_cleanup(legends)

    # ── Write output ──────────────────────────────────────────────────
    print(f"\n  [4/4] Writing {output_path} ...")
    output = {
        "generated":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total":      len(legends),
        "categories": CATEGORY_LABELS,
        "legends":    sorted(legends.values(), key=lambda x: x["name"])
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"      Total legends : {len(legends)}")
    print(f"      File written  : {output_path}")

    if supabase:
        write_to_supabase(legends, verbose, prune=supabase_prune)
    elif SUPABASE_URL:
        print(f"      Tip: run with --supabase to sync to Supabase")

    print(f"\n  Done.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Folklore Map — data pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_legends.py --seed-only              # fast, seeds + cleanup only
  python build_legends.py                          # Wikipedia pull
  python build_legends.py --hes                    # + Historic Environment Scotland
  python build_legends.py --historic-england       # + Historic England
  python build_legends.py --hes --historic-england --dbpedia --output legends.review.json
  python build_legends.py --seed-only --supabase --supabase-prune  # clean DB mirror
  python build_legends.py --hes --historic-england --dbpedia --supabase  # full run
        """
    )
    parser.add_argument("--seed-only",          action="store_true",
        help="Skip all API pulls, just process seed data")
    parser.add_argument("--hes",                action="store_true",
        help="Pull from Historic Environment Scotland INSPIRE WFS (Scotland)")
    parser.add_argument("--historic-england",   action="store_true",
        help="Pull from Historic England NHLE API (England & Wales)")
    parser.add_argument("--dbpedia",            action="store_true",
        help="Pull from DBpedia SPARQL (structured Wikipedia, better folklore coverage)")
    parser.add_argument("--supabase",           action="store_true",
        help="Sync to Supabase (needs SUPABASE_URL + SUPABASE_SERVICE_KEY env vars)")
    parser.add_argument("--supabase-prune",     action="store_true",
        help="Delete Supabase rows absent from local data (requires --supabase)")
    parser.add_argument("--limit",    type=int, default=500,
        help="Max articles per Wikipedia category (default: 500)")
    parser.add_argument("--output", default="legends.json",
        help="Write to this JSON file (default: legends.json)")
    parser.add_argument("--verbose", "-v",       action="store_true",
        help="Show each API call")
    args = parser.parse_args()
    if args.supabase_prune and not args.supabase:
        parser.error("--supabase-prune requires --supabase")
    if args.supabase and args.output != "legends.json":
        parser.error("--supabase requires --output legends.json")
    build(
        limit=args.limit,
        seed_only=args.seed_only,
        verbose=args.verbose,
        use_hes=args.hes,
        use_he=args.historic_england,
        use_dbpedia=args.dbpedia,
        supabase=args.supabase,
        supabase_prune=args.supabase_prune,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
