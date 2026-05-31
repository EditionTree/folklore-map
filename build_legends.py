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
USER_AGENT     = "FolkloreMap-BuildScript/1.0 (one-time data build; https://github.com)"
TIMEOUT        = 20
RATE_LIMIT     = 0.3    # seconds between requests

# UK bounding box for coordinate sanity check
UK_BOUNDS = {"lat_min": 49.5, "lat_max": 61.5, "lng_min": -10.5, "lng_max": 2.5}  # expanded to include Ireland


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
    "beast": "Beast",
    "ghost": "Ghost",
    "fairy": "Fae & Spirits",
    "water": "Water Creatures",
    "dragon": "Dragon",
    "witch": "Witch",
    "deity": "Deities",
    "giant": "Giant",
    "location": "Legendary Sites",
    "ancient_site": "Ancient & Sacred Sites",
    "hero": "Heroes & Legendary Figures",
    "pirate": "Pirates & Smugglers",
    "ritual": "Rituals & Folk Customs",
    "norse": "Norse & Northern Lore",
}


# ---------------------------------------------------------------------------
# Seed data — hand-curated, always included, takes priority over API results
# ---------------------------------------------------------------------------
SEED_LEGENDS = [
    {
        "name": "Alderley Edge",
        "lat": 53.296,
        "lng": -2.222,
        "category": "location",
        "region": "Cheshire",
        "summary": "A sandstone escarpment in Cheshire haunted by the legend of a sleeping king. A farmer leading a white horse to market was stopped by an old man who led him through a hidden door in the rock — revealing Arthur and his knights, sleeping until Britain needs them.",
        "source": "https://en.wikipedia.org/wiki/Alderley_Edge"
    },
    {
        "name": "Andraste",
        "lat": 52.24,
        "lng": 0.72,
        "category": "deity",
        "region": "East Anglia",
        "summary": "A warrior goddess invoked by Boudica before her revolt against Rome. Her name survives through Roman accounts, fierce and blood-bright at the edge of history and myth.",
        "source": "https://en.wikipedia.org/wiki/Andraste"
    },
    {
        "name": "Arawn",
        "lat": 51.881,
        "lng": -3.436,
        "category": "deity",
        "region": "Wales",
        "summary": "King of Annwn, the Welsh Otherworld, who exchanges places with Pwyll in the First Branch of the Mabinogi. He is not a devil, but a ruler of another order of being.",
        "source": "https://en.wikipedia.org/wiki/Arawn"
    },
    {
        "name": "Asrai",
        "lat": 53.48,
        "lng": -2.24,
        "category": "water",
        "region": "England",
        "summary": "A delicate water spirit said to melt away if captured or exposed to sunlight. The Asrai belongs to the colder, sadder edge of fairy lore, all moonlit water and vanishing hands.",
        "source": "https://en.wikipedia.org/wiki/Asrai"
    },
    {
        "name": "Avebury",
        "lat": 51.428,
        "lng": -1.854,
        "category": "ancient_site",
        "region": "Wiltshire",
        "summary": "The largest stone circle in the world — so vast a village was built inside it. The Devil is said to have danced here. At night the stones are said to move, drink from the stream, and return before dawn. No one has ever counted them twice and got the same number.",
        "source": "https://en.wikipedia.org/wiki/Avebury"
    },
    {
        "name": "Barghest",
        "lat": 54.284,
        "lng": -0.404,
        "category": "beast",
        "region": "Yorkshire",
        "summary": "A monstrous black dog of northern folklore, often linked to lonely roads, churchyards, and death omens. In some tales it is huge as a calf, with claws scraping stone and eyes like coals.",
        "source": "https://en.wikipedia.org/wiki/Barghest"
    },
    {
        "name": "Barns of Ayr",
        "lat": 55.4608,
        "lng": -4.6275,
        "category": "location",
        "region": "Scotland",
        "summary": "The Barns of Ayr was, according to Blind Harry in The Wallace, a site in Ayr, Scotland, which was used as English barracks. According to Blind Harry, a number of Scottish barons of Ayrshire were called to a meeting with King Edward I of England at a barn used as an English military barracks, only to be massacred and hanged, including Sir Ronald Crawford Sheriff of Ayr, Sir Bryce Blair of Blair, Sir Neil Montgomerie of Cassillis, Crystal of Set...",
        "source": "https://en.wikipedia.org/wiki/Barns_of_Ayr"
    },
    {
        "name": "Beast of Bodmin",
        "lat": 50.578,
        "lng": -4.602,
        "category": "beast",
        "region": "Cornwall",
        "summary": "A large phantom cat said to roam Bodmin Moor, blamed for mutilated livestock since the 1990s. Official investigations found no conclusive evidence, yet sightings persist to this day.",
        "source": "https://en.wikipedia.org/wiki/Beast_of_Bodmin"
    },
    {
        "name": "Beinn a' Bheithir",
        "lat": 56.6537,
        "lng": -5.1716,
        "category": "location",
        "region": "Highland, Scotland",
        "summary": "Beinn a' Bheithir is a mountain south of Ballachulish and Loch Leven in the Scottish Highlands. It has two Munro summits: Sgorr Dhearg at 1,024 m (3,360 ft) and Sgorr Dhonuill at 1,001 m (3,284 ft).",
        "source": "https://en.wikipedia.org/wiki/Beinn_a%27_Bheithir"
    },
    {
        "name": "Belenus",
        "lat": 51.381,
        "lng": -2.36,
        "category": "deity",
        "region": "Britain & Gaul",
        "summary": "A Celtic healing and solar god whose cult spread widely across the ancient Celtic world. Later antiquarians often connected him with bright fire, renewal, and sacred springs.",
        "source": "https://en.wikipedia.org/wiki/Belenus"
    },
    {
        "name": "Beltane Fire Festival",
        "lat": 55.955,
        "lng": -3.182,
        "category": "ritual",
        "region": "Edinburgh, Scotland",
        "summary": "A modern fire festival on Calton Hill inspired by ancient Beltane seasonal rites. It turns the coming of summer into theatre, flame, drums, and red-painted myth.",
        "source": "https://en.wikipedia.org/wiki/Beltane_Fire_Festival"
    },
    {
        "name": "Beowulf",
        "lat": 52.6,
        "lng": 1.3,
        "category": "hero",
        "region": "Anglo-Saxon England",
        "summary": "The great hero of the Old English epic, monster-slayer of Grendel, Grendel's mother, and finally a dragon. Though set in Scandinavia, the poem is a cornerstone of England's mythic inheritance.",
        "source": "https://en.wikipedia.org/wiki/Beowulf"
    },
    {
        "name": "Bisterne Dragon",
        "lat": 50.826,
        "lng": -1.754,
        "category": "dragon",
        "region": "Hampshire",
        "summary": "A New Forest dragon said to have terrorised Bisterne from its lair near Burley. Sir Maurice de Berkeley slew it after a brutal fight; the body became Bolton's Bench, and the knight returned there to die beneath a yew.",
        "source": "https://en.wikipedia.org/wiki/Bisterne_Dragon"
    },
    {
        "name": "The Black Dog of Newgate",
        "lat": 51.5157,
        "lng": -0.1019,
        "category": "beast",
        "region": "London",
        "summary": "The Black Dog of Newgate is a legend concerning the haunting of the former Newgate Prison of London, which was located next to the Old Bailey, close to St. Pauls Cathedral, in London, England.",
        "source": "https://en.wikipedia.org/wiki/The_Black_Dog_of_Newgate"
    },
    {
        "name": "Black Lady of Bradley Woods",
        "lat": 53.53,
        "lng": -0.13,
        "category": "ghost",
        "region": "Lincolnshire",
        "summary": "The Black Lady of Bradley Woods is a ghost which reportedly haunts the woods near the village of Bradley, Lincolnshire, England.",
        "source": "https://en.wikipedia.org/wiki/Black_Lady_of_Bradley_Woods"
    },
    {
        "name": "Black Rock Gorge",
        "lat": 57.6667,
        "lng": -4.37,
        "category": "location",
        "region": "Scotland",
        "summary": "Black Rock Gorge is a deep and narrow cleft in Old Red Sandstone conglomerate through which the Allt Graad flows at Evanton in Easter Ross, Scotland. It was formed by down-cutting by sediment-laden water during post-glacial rebound.",
        "source": "https://en.wikipedia.org/wiki/Black_Rock_Gorge"
    },
    {
        "name": "Black Shuck",
        "lat": 52.731,
        "lng": 1.286,
        "category": "beast",
        "region": "Norfolk",
        "summary": "A spectral black dog with blazing eyes the size of saucers, said to roam the coastline and heathlands of East Anglia. A single glance is an omen of death within the year.",
        "source": "https://en.wikipedia.org/wiki/Black_Shuck"
    },
    {
        "name": "Blue Ben of Kilve",
        "lat": 51.189,
        "lng": -3.225,
        "category": "dragon",
        "region": "Somerset",
        "summary": "A blue dragon said to have lived in the cliffs at Kilve and served as the Devil's steed. When it fell into the sea, locals later pointed to fossil bones as proof of the beast.",
        "source": "https://en.wikipedia.org/wiki/List_of_dragons_in_mythology_and_folklore"
    },
    {
        "name": "Bluecap",
        "lat": 54.978,
        "lng": -1.617,
        "category": "fairy",
        "region": "Northumberland",
        "summary": "A mine spirit seen as a small blue flame in the pit. Unlike crueler goblins, Bluecaps were often helpful workers, but expected fair wages left for them like any miner.",
        "source": "https://en.wikipedia.org/wiki/Bluecap"
    },
    {
        "name": "Boggart of Boggart Hole Clough",
        "lat": 53.52,
        "lng": -2.193,
        "category": "fairy",
        "region": "Manchester",
        "summary": "A mischievous household spirit that plagued a farming family — souring milk, tangling hair, pinching children. When the family tried to move away, the Boggart announced it was coming with them.",
        "source": "https://en.wikipedia.org/wiki/Boggart"
    },
    {
        "name": "Bossiney Castle",
        "lat": 50.6663,
        "lng": -4.7385,
        "category": "location",
        "region": "Cornwall",
        "summary": "A Cornish site tied to Arthurian and local tradition around Tintagel country. Folklore in the area tells of hidden courts, vanished strongholds, and kings sleeping beneath the land until called again.",
        "source": "https://en.wikipedia.org/wiki/Bossiney_Castle"
    },
    {
        "name": "Bran the Blessed",
        "lat": 51.508,
        "lng": -0.076,
        "category": "hero",
        "region": "London",
        "summary": "A giant king of Britain so vast no house could contain him. He carried his armies across the Irish Sea on his own back. His severed head, buried beneath the Tower of London, was said to protect Britain from invasion — until Arthur dug it up.",
        "source": "https://en.wikipedia.org/wiki/Brân_the_Blessed"
    },
    {
        "name": "Brigid",
        "lat": 53.324,
        "lng": -6.463,
        "category": "deity",
        "region": "Ireland & Britain",
        "summary": "Goddess of fire, poetry, healing and smithcraft — one of the most beloved figures in Celtic tradition. Her festival Imbolc marks the first breath of spring. Christianised as Saint Brigid, her flame was tended for centuries at Kildare.",
        "source": "https://en.wikipedia.org/wiki/Brigid"
    },
    {
        "name": "Brown Lady of Raynham Hall",
        "lat": 52.796,
        "lng": 0.79,
        "category": "ghost",
        "region": "Norfolk",
        "summary": "The Brown Lady of Raynham Hall is a ghost that reportedly haunts Raynham Hall in Norfolk, England. \nIt became one of the most famous hauntings in the United Kingdom when photographers from Country Life magazine claimed to have captured its image. The \"Brown Lady\" is so named because of the brown brocade dress it is claimed she wears.",
        "source": "https://en.wikipedia.org/wiki/Brown_Lady_of_Raynham_Hall"
    },
    {
        "name": "Brownie",
        "lat": 55.953,
        "lng": -3.189,
        "category": "fairy",
        "region": "Scotland & Northern England",
        "summary": "A household spirit that works by night in exchange for food, respect, and privacy. Offer clothes or insult its labour and the brownie may vanish, or become something much less helpful.",
        "source": "https://en.wikipedia.org/wiki/Brownie_(folklore)"
    },
    {
        "name": "Bryn Cader Faner",
        "lat": 52.8982,
        "lng": -4.0114,
        "category": "ancient_site",
        "region": "Wales",
        "summary": "The Bryn Cader Faner is a Bronze Age round cairn which lies to the east of the small hamlet of Talsarnau in the Ardudwy area of Gwynedd in Wales. The diameter is 8.7 metres (29 ft) and there are 18 thin jagged pillars which jut upwards from the low cairn. It is thought to date back to the late third millennium BC.\nThe site was disturbed by 19th-century treasure hunters, who left a hole in the centre, indicating the position of a cist or a grave.",
        "source": "https://en.wikipedia.org/wiki/Bryn_Cader_Faner"
    },
    {
        "name": "Bryn Gwyn stones",
        "lat": 53.1772,
        "lng": -4.3021,
        "category": "ancient_site",
        "region": "Wales",
        "summary": "The Bryn Gwyn Stones or Bryn Gwyn Standing Stones are neolithic stones in Brynsiencyn on Anglesey.",
        "source": "https://en.wikipedia.org/wiki/Bryn_Gwyn_stones"
    },
    {
        "name": "Bucca",
        "lat": 50.119,
        "lng": -5.537,
        "category": "fairy",
        "region": "Cornwall",
        "summary": "A Cornish spirit of the sea, mines, and weather, sometimes treated as a hobgoblin and sometimes as something older and darker. Fisherfolk left offerings to keep Bucca friendly.",
        "source": "https://en.wikipedia.org/wiki/Bucca_(mythological_creature)"
    },
    {
        "name": "The Buggane of St Trinian's",
        "lat": 54.231,
        "lng": -4.531,
        "category": "beast",
        "region": "Isle of Man",
        "summary": "A fearsome shape-shifting spirit haunting the ruined church of St Trinian's on the Isle of Man, repeatedly tearing off its roof whenever rebuilt. The church has stood roofless for centuries.",
        "source": "https://en.wikipedia.org/wiki/Buggane"
    },
    {
        "name": "Bwbach",
        "lat": 51.482,
        "lng": -3.179,
        "category": "fairy",
        "region": "Wales",
        "summary": "A Welsh household spirit similar to a brownie, rewarding good housekeeping and punishing idleness or disrespect. In later tales it gained a sharp dislike for teetotallers and dissenting ministers.",
        "source": "https://en.wikipedia.org/wiki/Bwbach"
    },
    {
        "name": "Caer Bran",
        "lat": 50.1047,
        "lng": -5.627,
        "category": "location",
        "region": "Cornwall",
        "summary": "An Iron Age hillfort whose name evokes Bran, the giant king of Welsh tradition. The site sits in a landscape thick with Cornish legend, standing stones, and tales of buried ancient power.",
        "source": "https://en.wikipedia.org/wiki/Caer_Bran"
    },
    {
        "name": "Caerleon",
        "lat": 51.6103,
        "lng": -2.9558,
        "category": "location",
        "region": "Wales",
        "summary": "A Roman fortress town deeply folded into Arthurian tradition. Geoffrey of Monmouth made it one of Arthur's chief courts, turning its ruins into a gateway between Roman Britain and medieval romance.",
        "source": "https://en.wikipedia.org/wiki/Caerleon"
    },
    {
        "name": "Cailleach",
        "lat": 57.119,
        "lng": -5.525,
        "category": "deity",
        "region": "Highland, Scotland",
        "summary": "The divine hag of winter — one of the oldest supernatural beings in Celtic mythology. She shaped the mountains of Scotland by striding across the land, dropping boulders from her apron. Ben Nevis is said to be her throne.",
        "source": "https://en.wikipedia.org/wiki/Cailleach"
    },
    {
        "name": "Canewdon",
        "lat": 51.6162,
        "lng": 0.7444,
        "category": "witch",
        "region": "Essex",
        "summary": "Canewdon is a village and civil parish in the Rochford district of Essex, England. The village is located approximately 4 miles (6.4 km) northeast of the town of Rochford, while the parish extends for several miles on the southern side of the River Crouch. At the 2021 census the parish had a population of 1,656.",
        "source": "https://en.wikipedia.org/wiki/Canewdon"
    },
    {
        "name": "Cantre'r Gwaelod",
        "lat": 52.5,
        "lng": -4.5,
        "category": "deity",
        "region": "Wales",
        "summary": "Cantre'r Gwaelod, also known as Cantref Gwaelod or Cantref y Gwaelod, is a legendary ancient sunken kingdom said to have occupied a tract of fertile land lying between Ramsey Island and Bardsey Island in what is now Cardigan Bay to the west of Wales. It has been described as a \"Welsh Atlantis\" and has featured in folklore, literature, and song.",
        "source": "https://en.wikipedia.org/wiki/Cantre%27r_Gwaelod"
    },
    {
        "name": "Castle Downs, Cornwall",
        "lat": 50.4248,
        "lng": -4.8938,
        "category": "location",
        "region": "Cornwall",
        "summary": "A Cornish hillfort landscape linked to Castle an Dinas and the old legendary geography of giants, saints, and hidden strongholds. Its height and isolation made it a natural home for stories.",
        "source": "https://en.wikipedia.org/wiki/Castle_Downs%2C_Cornwall"
    },
    {
        "name": "The Cauld Lad of Hylton",
        "lat": 54.906,
        "lng": -1.432,
        "category": "ghost",
        "region": "Sunderland",
        "summary": "The spirit of a stable boy killed by a lord of Hylton Castle. He haunted the kitchens, tidying if work was left undone — until given a cloak and hood, whereupon he vanished forever.",
        "source": "https://en.wikipedia.org/wiki/Cauld_Lad_of_Hylton"
    },
    {
        "name": "Ceridwen",
        "lat": 52.74,
        "lng": -3.852,
        "category": "deity",
        "region": "Powys, Wales",
        "summary": "The Welsh enchantress who brewed the cauldron of inspiration and knowledge, Awen. When her servant Gwion Bach accidentally tasted three drops, she pursued him through a cycle of transformations before swallowing him whole — and giving birth to the great poet Taliesin.",
        "source": "https://en.wikipedia.org/wiki/Ceridwen"
    },
    {
        "name": "Cerne Abbas Giant",
        "lat": 50.8137,
        "lng": -2.4747,
        "category": "giant",
        "region": "Dorset",
        "summary": "The Cerne Abbas Giant, or Cerne Giant, is a hill figure near the village of Cerne Abbas, in Dorset, England. It is currently owned by the National Trust, and listed as a scheduled monument of England. Measuring 55 metres (180 ft) in length, the hill figure depicts a bald, nude male with a prominent erection, holding his left hand out to the side and wielding a large club in his right hand.",
        "source": "https://en.wikipedia.org/wiki/Cerne_Abbas_Giant"
    },
    {
        "name": "Cernunnos",
        "lat": 51.507,
        "lng": -0.128,
        "category": "deity",
        "region": "Britain & Gaul",
        "summary": "The antlered Celtic god associated with wild nature, animals, fertility, and the deep green world. His image appears on ancient objects, a horned figure seated among beasts and mystery.",
        "source": "https://en.wikipedia.org/wiki/Cernunnos"
    },
    {
        "name": "Chanctonbury Ring",
        "lat": 50.893,
        "lng": -0.381,
        "category": "location",
        "region": "West Sussex",
        "summary": "An Iron Age hillfort ringed with beech trees on the South Downs. Walk seven times around it at midnight and the Devil will appear with a bowl of soup. Roman offerings were found buried within. The trees were blown down in 1987 — and something changed.",
        "source": "https://en.wikipedia.org/wiki/Chanctonbury_Ring"
    },
    {
        "name": "Cheesewring",
        "lat": 50.5254,
        "lng": -4.4593,
        "category": "location",
        "region": "Cornwall",
        "summary": "A strange granite tor on Bodmin Moor, said in local legend to have been formed during a stone-throwing contest between a giant and a saint. The impossible stack looks less built than argued into being.",
        "source": "https://en.wikipedia.org/wiki/Cheesewring"
    },
    {
        "name": "Cheetham Close",
        "lat": 53.6388,
        "lng": -2.431,
        "category": "ancient_site",
        "region": "Lancashire",
        "summary": "Cheetham Close is a megalithic site and scheduled ancient monument located in Lancashire, very close to the boundary with Greater Manchester, England. The megalith was in good condition until a farmer from Turton sledgehammered the circle in the 1870s. According to an article published in 1829, Cheetham Close was once a druidical ritual place and a Roman road passed 'within two hundred yards' of the megalith.",
        "source": "https://en.wikipedia.org/wiki/Cheetham_Close"
    },
    {
        "name": "Church Grim",
        "lat": 51.752,
        "lng": -1.258,
        "category": "ghost",
        "region": "England & Scandinavia",
        "summary": "A guardian spirit said to haunt churchyards, often appearing as a black dog. Folklore claims an animal was sometimes buried first in a new graveyard so its ghost would protect the dead.",
        "source": "https://en.wikipedia.org/wiki/Church_grim"
    },
    {
        "name": "Chûn Quoit",
        "lat": 50.1486,
        "lng": -5.6377,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "Chûn Quoit is one of the best preserved of all Neolithic quoits in western Cornwall, England, United Kingdom.",
        "source": "https://en.wikipedia.org/wiki/Ch%C3%BBn_Quoit"
    },
    {
        "name": "Cock Lane ghost",
        "lat": 51.5172,
        "lng": -0.1024,
        "category": "ghost",
        "region": "Norfolk",
        "summary": "The Cock Lane ghost was a purported haunting that attracted mass public attention in 1762. The location was a lodging in Cock Lane, a short road adjacent to London's Smithfield market and a few minutes' walk from St Paul's Cathedral. The event centred on three people: William Kent, a usurer from Norfolk; Richard Parsons, a parish clerk; and Parsons' daughter Elizabeth.",
        "source": "https://en.wikipedia.org/wiki/Cock_Lane_ghost"
    },
    {
        "name": "Coventina",
        "lat": 55.026,
        "lng": -2.22,
        "category": "deity",
        "region": "Northumberland",
        "summary": "A Romano-British goddess of wells and springs, especially associated with Coventina's Well near Carrawburgh on Hadrian's Wall. Offerings to her were dropped into sacred water.",
        "source": "https://en.wikipedia.org/wiki/Coventina"
    },
    {
        "name": "Craddock Moor stone circle",
        "lat": 50.5199,
        "lng": -4.4717,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "Craddock Moor Stone Circle or Craddock Moor Circle is a stone circle located near Minions on Bodmin Moor in Cornwall, UK. It is situated around half a mile Northwest of The Hurlers.",
        "source": "https://en.wikipedia.org/wiki/Craddock_Moor_stone_circle"
    },
    {
        "name": "Cŵn Annwn",
        "lat": 51.882,
        "lng": -3.436,
        "category": "beast",
        "region": "Brecon Beacons, Wales",
        "summary": "The spectral hounds of Annwn, the Welsh Otherworld. Their baying grows quieter as they draw nearer — silence means they are upon you.",
        "source": "https://en.wikipedia.org/wiki/Cŵn_Annwn"
    },
    {
        "name": "Dando's Dogs",
        "lat": 50.337,
        "lng": -4.632,
        "category": "ghost",
        "region": "Cornwall",
        "summary": "A spectral hunt led by the wicked priest Dando, doomed to ride forever with infernal hounds after refusing to give up his game to the Devil.",
        "source": "https://en.wikipedia.org/wiki/Dando%27s_Dogs"
    },
    {
        "name": "Devil's Arrows",
        "lat": 54.095,
        "lng": -1.392,
        "category": "ancient_site",
        "region": "North Yorkshire",
        "summary": "Three great standing stones near Boroughbridge, said to have been hurled by the Devil at the town of Aldborough. He missed, which is exactly the kind of thing folklore remembers forever.",
        "source": "https://en.wikipedia.org/wiki/Devil%27s_Arrows"
    },
    {
        "name": "Ding Dong mines",
        "lat": 50.1542,
        "lng": -5.5928,
        "category": "location",
        "region": "Cornwall",
        "summary": "An ancient Cornish mining landscape with traditions connecting it to Joseph of Arimathea and old tin-working lore. Mine country often births knockers, hidden spirits, and stories of wealth beneath the hill.",
        "source": "https://en.wikipedia.org/wiki/Ding_Dong_mines"
    },
    {
        "name": "Doom Bar",
        "lat": 50.5625,
        "lng": -4.94,
        "category": "water",
        "region": "Cornwall",
        "summary": "A dangerous sandbar at the mouth of the River Camel, linked to the Mermaid of Padstow. In legend, a dying mermaid cursed the harbour after being shot, raising the bar to wreck ships forever.",
        "source": "https://en.wikipedia.org/wiki/Doom_Bar"
    },
    {
        "name": "Dozmary Pool",
        "lat": 50.5423,
        "lng": -4.5502,
        "category": "water",
        "region": "Cornwall",
        "summary": "A lonely pool on Bodmin Moor, often named as one of the places where Arthur's sword Excalibur was returned to the Lady of the Lake. It is also tied to ghostly and infernal stories.",
        "source": "https://en.wikipedia.org/wiki/Dozmary_Pool"
    },
    {
        "name": "Dragon Hill, Uffington",
        "lat": 51.576,
        "lng": -1.565,
        "category": "dragon",
        "region": "Oxfordshire",
        "summary": "A low chalk hill below the Uffington White Horse, said to be where Saint George slew the dragon. The bare chalk patch on top marks where the dragon's blood poisoned the grass.",
        "source": "https://en.wikipedia.org/wiki/Dragon_Hill,_Uffington"
    },
    {
        "name": "Dragon of Mordiford",
        "lat": 52.034,
        "lng": -2.618,
        "category": "dragon",
        "region": "Herefordshire",
        "summary": "A girl named Maud is said to have found a tiny serpent and raised it in secret until it grew into a dragon. It took to the hills above Mordiford, feeding on livestock and men while sparing only her.",
        "source": "https://en.wikipedia.org/wiki/Dragon_of_Mordiford"
    },
    {
        "name": "Dragon of Wantley",
        "lat": 53.482,
        "lng": -1.563,
        "category": "dragon",
        "region": "South Yorkshire",
        "summary": "A comic Yorkshire dragon from ballad tradition, slain by More of More Hall after being kicked in its vulnerable backside. It is dragon-slaying with muddy boots and tavern laughter.",
        "source": "https://en.wikipedia.org/wiki/Dragon_of_Wantley"
    },
    {
        "name": "The Dullahan",
        "lat": 54.607,
        "lng": -5.926,
        "category": "ghost",
        "region": "Northern Ireland",
        "summary": "A headless horseman carrying his own severed head, which glows like a lantern. Where the Dullahan stops and calls your name, you die. No lock or gate can bar his passage.",
        "source": "https://en.wikipedia.org/wiki/Dullahan"
    },
    {
        "name": "Dunnie",
        "lat": 55.168,
        "lng": -1.688,
        "category": "fairy",
        "region": "Northumberland",
        "summary": "A shape-shifting Northumbrian spirit that often appears as a horse or donkey. It delights in tricks, carrying riders only to vanish and dump them into mud or water.",
        "source": "https://en.wikipedia.org/wiki/Dunnie"
    },
    {
        "name": "Dunstan and the Devil",
        "lat": 51.425,
        "lng": -2.671,
        "category": "hero",
        "region": "Somerset",
        "summary": "Saint Dunstan was said to have seized the Devil by the nose with blacksmith's tongs. The tale explains horseshoes as protection and gives English folklore one of its best infernal workplace accidents.",
        "source": "https://en.wikipedia.org/wiki/Dunstan"
    },
    {
        "name": "Enfield Poltergeist",
        "lat": 51.6553,
        "lng": -0.0355,
        "category": "ghost",
        "region": "London",
        "summary": "The Enfield poltergeist was a claim of supernatural activity at 284 Green Street, a council house in Brimsdown, Enfield, London, England, between 1977 and 1979. The alleged poltergeist activity was centred on sisters Janet, aged 11, and Margaret Hodgson, aged 13.",
        "source": "https://en.wikipedia.org/wiki/Enfield_poltergeist"
    },
    {
        "name": "Epona",
        "lat": 51.507,
        "lng": -0.128,
        "category": "deity",
        "region": "Roman Britain",
        "summary": "A Celtic horse goddess worshipped across the Roman world, including Britain. She protected horses, riders, cavalry, and journeys, often shown with mares, foals, or a cornucopia.",
        "source": "https://en.wikipedia.org/wiki/Epona"
    },
    {
        "name": "Fairy Bridge",
        "lat": 54.1144,
        "lng": -4.5953,
        "category": "fairy",
        "region": "Isle of Man",
        "summary": "A small Isle of Man bridge where travellers traditionally greet the fairies as they pass. Failing to acknowledge the Little People is considered unlucky, especially on journeys across the island.",
        "source": "https://en.wikipedia.org/wiki/Fairy_Bridge_%28Isle_of_Man%29"
    },
    {
        "name": "Fat Lips",
        "lat": 55.5771,
        "lng": -2.6494,
        "category": "fairy",
        "region": "Scotland",
        "summary": "Fat Lips is the name given to a legendary spirit dwelling in Dryburgh Abbey in Berwickshire, Scotland.",
        "source": "https://en.wikipedia.org/wiki/Fat_Lips"
    },
    {
        "name": "Finfolk",
        "lat": 58.984,
        "lng": -2.959,
        "category": "water",
        "region": "Orkney",
        "summary": "Powerful sea-sorcerers of Orcadian folklore who move between the underwater realm of Finfolkaheem and the vanishing island of Hildaland. They steal mortals for spouses and servants.",
        "source": "https://en.wikipedia.org/wiki/Finfolk"
    },
    {
        "name": "Fingal",
        "lat": 56.432,
        "lng": -6.341,
        "category": "hero",
        "region": "Staffa, Scotland",
        "summary": "The great Gaelic giant-hero Fionn mac Cumhaill, known in Scotland as Fingal. He built the causeway between Scotland and Ireland so he could fight his Ulster rival — the hexagonal columns of Fingal's Cave and the Giant's Causeway are said to be his road.",
        "source": "https://en.wikipedia.org/wiki/Fionn_mac_Cumhaill"
    },
    {
        "name": "Fintan's Grave",
        "lat": 52.8467,
        "lng": -8.3905,
        "category": "location",
        "region": "Arra Mountains",
        "summary": "Fintan's Grave is a mythological cave on the Irish mountain Tul Tuinde in the Arra Mountains near Lough Derg.",
        "source": "https://en.wikipedia.org/wiki/Fintan%27s_Grave"
    },
    {
        "name": "Folkestone White Horse",
        "lat": 51.1012,
        "lng": 1.1397,
        "category": "ancient_site",
        "region": "Kent",
        "summary": "The Folkestone White Horse is a white horse hill figure, carved into Cheriton Hill, Folkestone, Kent, South East England. It overlooks the English terminal of the Channel Tunnel and was completed in June 2003.",
        "source": "https://en.wikipedia.org/wiki/Folkestone_White_Horse"
    },
    {
        "name": "The Giant of Cerne Abbas",
        "lat": 50.813,
        "lng": -2.475,
        "category": "giant",
        "region": "Dorset",
        "summary": "A vast chalk figure carved into a Dorset hillside — a naked giant clutching a club, 55 metres tall. His origins are disputed: Iron Age fertility god, Roman Hercules, or Civil War satire. For centuries, sleeping on the hill was said to cure infertility.",
        "source": "https://en.wikipedia.org/wiki/Cerne_Abbas_Giant"
    },
    {
        "name": "Giant's Causeway",
        "lat": 55.2408,
        "lng": -6.5117,
        "category": "giant",
        "region": "Ireland",
        "summary": "A volcanic shore of interlocking basalt columns explained in legend as the road built by Fionn mac Cumhaill to reach his Scottish giant rival. Geology and giantcraft shake hands here.",
        "source": "https://en.wikipedia.org/wiki/Giant%27s_Causeway"
    },
    {
        "name": "Glastonbury Tor",
        "lat": 51.144,
        "lng": -2.699,
        "category": "location",
        "region": "Somerset",
        "summary": "The sacred hill rising from the Somerset Levels — said to be the Isle of Avalon where Arthur was carried after his final battle. An entrance to the fairy underworld is hidden in its flanks. Saint Collen once descended into it and found a shining court.",
        "source": "https://en.wikipedia.org/wiki/Glastonbury_Tor"
    },
    {
        "name": "Gogmagog",
        "lat": 50.06,
        "lng": -5.713,
        "category": "hero",
        "region": "Cornwall",
        "summary": "The last of the giants of Albion, said to have roamed Cornwall before being cast into the sea by the Trojan hero Corineus. Effigies of Gog and Magog still march in the Lord Mayor's Show — ancient guardians of the City of London.",
        "source": "https://en.wikipedia.org/wiki/Gogmagog_(giant)"
    },
    {
        "name": "Granny Kempock Stone",
        "lat": 55.9614,
        "lng": -4.8198,
        "category": "witch",
        "region": "Gourock, Scotland",
        "summary": "The megalithic Kempock Stone, popularly known as Granny Kempock, stands on a cliff behind Kempock Street, the main shopping street in Gourock, Scotland. The stone, or menhir, is grey mica schist and of indeterminate origin, but it has been suggested that it is an old altar to the pagan god Baal, or a memorial to an ancient battle.",
        "source": "https://en.wikipedia.org/wiki/Granny_Kempock_Stone"
    },
    {
        "name": "Green Children of Woolpit",
        "lat": 52.233,
        "lng": 0.916,
        "category": "fairy",
        "region": "Suffolk",
        "summary": "In the 12th century, two children with green skin emerged from pits near Woolpit, speaking an unknown tongue. The girl survived and spoke of an underground land called St Martin's Land.",
        "source": "https://en.wikipedia.org/wiki/Green_children_of_Woolpit"
    },
    {
        "name": "The Green Knight",
        "lat": 52.0,
        "lng": -2.0,
        "category": "hero",
        "region": "Britain",
        "summary": "A huge green challenger who enters Arthur's court carrying a holly branch and an axe. His beheading game with Gawain tests courage, courtesy, truth, and the strangeness of winter.",
        "source": "https://en.wikipedia.org/wiki/Green_Knight"
    },
    {
        "name": "The Green Man",
        "lat": 51.881,
        "lng": -2.074,
        "category": "deity",
        "region": "Gloucestershire",
        "summary": "A face wreathed in leaves, carved into church columns and cathedral arches across Britain. He represents the untamed spirit of nature, the cycle of growth and decay — ancient beyond Christianity, impossible to fully explain away.",
        "source": "https://en.wikipedia.org/wiki/Green_Man"
    },
    {
        "name": "Grubstones",
        "lat": 53.8984,
        "lng": -1.794,
        "category": "ancient_site",
        "region": "Yorkshire",
        "summary": "The Grubstones is a stone circle on Burley Moor in West Yorkshire, England. It is believed to be either an embanked stone circle or a ring cairn.",
        "source": "https://en.wikipedia.org/wiki/Grubstones"
    },
    {
        "name": "Gulf of Corryvreckan",
        "lat": 56.155,
        "lng": -5.7278,
        "category": "location",
        "region": "Scotland",
        "summary": "One of the world's great whirlpools, feared in Gaelic tradition and tied to tales of sea trials, drowned princes, and the Cailleach washing her plaid in the roaring waters.",
        "source": "https://en.wikipedia.org/wiki/Gulf_of_Corryvreckan"
    },
    {
        "name": "Gwrach-y-Rhibyn",
        "lat": 52.415,
        "lng": -4.082,
        "category": "ghost",
        "region": "Ceredigion, Wales",
        "summary": "Wales's own banshee — a hideous hag with leathery wings who shrieks at crossroads to foretell the death of those with Welsh blood. Her wail carries across the hills on still nights.",
        "source": "https://en.wikipedia.org/wiki/Gwrach-y-Rhibyn"
    },
    {
        "name": "Henderson Stone",
        "lat": 56.6812,
        "lng": -5.096,
        "category": "location",
        "region": "Scotland",
        "summary": "The Henderson Stone is a granite boulder in a field in the Glencoe (Carnoch) area of Scotland. Clach Eanruig is translated alternatively as Henderson Stone or Henry's Stone.",
        "source": "https://en.wikipedia.org/wiki/Henderson_Stone"
    },
    {
        "name": "Herne the Hunter",
        "lat": 51.483,
        "lng": -0.604,
        "category": "ghost",
        "region": "Berkshire",
        "summary": "The ghost of a royal huntsman who hanged himself from an ancient oak in Windsor Forest. He rides through the night with a spectral pack of hounds, his antlered helm gleaming.",
        "source": "https://en.wikipedia.org/wiki/Herne_the_Hunter"
    },
    {
        "name": "Hobby Horse of Padstow",
        "lat": 50.542,
        "lng": -4.937,
        "category": "ritual",
        "region": "Cornwall",
        "summary": "A May Day custom in which the 'Obby 'Oss dances through Padstow with music, pursuit, and ritual energy. It is one of Britain's most famous surviving folk ceremonies.",
        "source": "https://en.wikipedia.org/wiki/%27Obby_%27Oss_festival"
    },
    {
        "name": "Jenny Greenteeth",
        "lat": 53.762,
        "lng": -2.703,
        "category": "water",
        "region": "Lancashire",
        "summary": "A river hag lurking beneath the surface of ponds and slow rivers. She drags the unwary — particularly children — to their deaths in the depths.",
        "source": "https://en.wikipedia.org/wiki/Jenny_Greenteeth"
    },
    {
        "name": "Jingling Geordie's Hole",
        "lat": 55.018,
        "lng": -1.417,
        "category": "location",
        "region": "Tynemouth",
        "summary": "A cave at Tynemouth associated with the miserly spirit Jingling Geordie, whose hoarded coins were said to rattle in the dark. A coastal pocket of ghost-story greed.",
        "source": "https://en.wikipedia.org/wiki/Jingling_Geordie%27s_Hole"
    },
    {
        "name": "Julian's Bower",
        "lat": 53.6849,
        "lng": -0.6694,
        "category": "ancient_site",
        "region": "Lincolnshire",
        "summary": "Julian's Bower or Julian Bower is a name given to turf mazes in several different parts of England. Only one of this name still exists, at Alkborough in North Lincolnshire. It has also been known by corrupted forms of the name, such as \"Gillian's Bore\" and \"Gilling Bore\".",
        "source": "https://en.wikipedia.org/wiki/Julian%27s_Bower"
    },
    {
        "name": "Keith Marischal",
        "lat": 55.8697,
        "lng": -2.8819,
        "category": "witch",
        "region": "Scotland",
        "summary": "Keith Marischal is a Scottish Baronial country house lying in the parish of Humbie, East Lothian, Scotland. The original building was an \"L-shaped\" tower house, built long before 1589 when it was extended into a U-shaped courtyard house. The building acquired its modern appearance in the 19th century when the courtyard was filled in. The house is protected as a category B listed building.",
        "source": "https://en.wikipedia.org/wiki/Keith_Marischal"
    },
    {
        "name": "Kelpie",
        "lat": 57.603,
        "lng": -4.621,
        "category": "water",
        "region": "Highland, Scotland",
        "summary": "A shape-shifting water horse lurking in Scottish lochs. It appears as a magnificent steed to lure riders onto its back before plunging into the depths. Its skin is adhesive — those who mount it cannot let go.",
        "source": "https://en.wikipedia.org/wiki/Kelpie"
    },
    {
        "name": "Kirkcudbright Tolbooth",
        "lat": 54.8356,
        "lng": -4.0558,
        "category": "witch",
        "region": "Scotland",
        "summary": "Kirkcudbright Tolbooth is a historic municipal building in Kirkcudbright in Kirkcudbrightshire in the administrative area of Dumfries and Galloway, Scotland. Built between 1627 and 1629 to serve the town as a centre of commercial administration, a meeting place for the council, and a prison, it was used for all these roles until the late eighteenth century when the council moved much of its business to new, larger premises they had constructed...",
        "source": "https://en.wikipedia.org/wiki/Kirkcudbright_Tolbooth"
    },
    {
        "name": "Knocker",
        "lat": 50.119,
        "lng": -5.537,
        "category": "fairy",
        "region": "Cornwall",
        "summary": "Mine spirits whose tapping warned Cornish miners of danger, rich seams, or unseen company in the dark. They could be helpful if respected and dangerous if mocked.",
        "source": "https://en.wikipedia.org/wiki/Knocker_(folklore)"
    },
    {
        "name": "Knucker of Lyminster",
        "lat": 50.829,
        "lng": -0.545,
        "category": "dragon",
        "region": "West Sussex",
        "summary": "A water-dragon haunting a bottomless knucker-hole near Lyminster. Local tales say it devoured cattle and people until slain by a hero who used poisoned pudding, swordplay, or both, depending on who tells it.",
        "source": "https://en.wikipedia.org/wiki/Knucker"
    },
    {
        "name": "Kraken",
        "lat": 59.101,
        "lng": -3.189,
        "category": "water",
        "region": "Orkney",
        "summary": "A vast many-armed creature rising from the deep. Norse sagas describe it as large enough to be mistaken for an island — only revealing itself when it submerged beneath the waves.",
        "source": "https://en.wikipedia.org/wiki/Kraken"
    },
    {
        "name": "Laidly Worm of Spindleston Heugh",
        "lat": 55.596,
        "lng": -1.706,
        "category": "dragon",
        "region": "Northumberland",
        "summary": "A princess transformed by her jealous stepmother into a loathsome worm around Bamburgh. Her brother Childe Wynd broke the spell with three kisses, returning monster to maiden and justice to the hall.",
        "source": "https://en.wikipedia.org/wiki/Laidly_Worm_of_Spindleston_Heugh"
    },
    {
        "name": "Lambton Worm",
        "lat": 54.837,
        "lng": -1.576,
        "category": "dragon",
        "region": "County Durham",
        "summary": "A monstrous serpent pulled from the River Wear by young John Lambton. It grew to wrap itself around Penshaw Hill, devouring livestock and children alike.",
        "source": "https://en.wikipedia.org/wiki/Lambton_Worm"
    },
    {
        "name": "Lancashire Witches Walk",
        "lat": 53.968,
        "lng": -2.436,
        "category": "witch",
        "region": "Lancashire",
        "summary": "The Lancashire Witches Walk is a 51-mile (82 km) long-distance footpath opened in 2012, between Barrowford and Lancaster, all in Lancashire, England. It starts at Pendle Heritage Centre in Barrowford before passing through the Forest of Pendle, the town of Clitheroe and the Forest of Bowland to finish at Lancaster Castle.",
        "source": "https://en.wikipedia.org/wiki/Lancashire_Witches_Walk"
    },
    {
        "name": "Latoon Fairy Bush",
        "lat": 52.7901,
        "lng": -8.9213,
        "category": "fairy",
        "region": "Ireland",
        "summary": "The Latoon fairy bush, or Latoon fairy tree, is a whitethorn tree situated beside the M18 motorway in Latoon, County Clare, Ireland that was the subject of a preservation campaign led by Irish folklorist Eddie Lenihan in 1999 to save it from being cut down when the motorway was being built. According to Lenihan, the tree is an \"important meeting place for supernatural forces of the region\".",
        "source": "https://en.wikipedia.org/wiki/Latoon_fairy_bush"
    },
    {
        "name": "Lia Fáil",
        "lat": 53.5786,
        "lng": -6.6121,
        "category": "ancient_site",
        "region": "Ireland",
        "summary": "The Fál or Lia Fáil is a stone at the Inauguration Mound on the Hill of Tara in County Meath, Ireland, which served as the coronation stone for the King of Tara and hence High King of Ireland. It is also known as the Stone of Destiny or Speaking Stone. According to legend, all of the kings of Ireland were crowned on the stone up to Muirchertach mac Ercae, c. 500 AD.",
        "source": "https://en.wikipedia.org/wiki/Lia_F%C3%A1il"
    },
    {
        "name": "Llyn y Fan Fach",
        "lat": 51.8819,
        "lng": -3.7419,
        "category": "water",
        "region": "Wales",
        "summary": "A Welsh lake famed for the Lady of the Lake, who married a mortal under strict conditions before returning beneath the water. Their sons became the legendary Physicians of Myddfai.",
        "source": "https://en.wikipedia.org/wiki/Llyn_y_Fan_Fach"
    },
    {
        "name": "Loch Morar",
        "lat": 56.95,
        "lng": -5.6722,
        "category": "water",
        "region": "Highland, Scotland",
        "summary": "Britain's deepest freshwater loch and home of Morag, a lake spirit or monster traditionally treated less as a curiosity and more as a death omen for local families.",
        "source": "https://en.wikipedia.org/wiki/Loch_Morar"
    },
    {
        "name": "The Loch Ness Monster",
        "lat": 57.321,
        "lng": -4.424,
        "category": "water",
        "region": "Highland, Scotland",
        "summary": "A vast creature said to inhabit the deep waters of Loch Ness. First recorded in 565 AD, Nessie has been hunted by cameras, submarines and sonar for over a century — always elusive.",
        "source": "https://en.wikipedia.org/wiki/Loch_Ness_monster"
    },
    {
        "name": "Lochmaben Stone",
        "lat": 54.9839,
        "lng": -3.0761,
        "category": "deity",
        "region": "Scotland",
        "summary": "A megalith on the Solway Firth linked by name and tradition to Maponos or Mabon, a youthful Celtic divine figure. It also marks a landscape of border law, ritual, and deep time.",
        "source": "https://en.wikipedia.org/wiki/Lochmaben_Stone"
    },
    {
        "name": "The Loe",
        "lat": 50.0764,
        "lng": -5.2894,
        "category": "water",
        "region": "Cornwall",
        "summary": "Cornwall's largest natural freshwater lake, separated from the sea by a shingle bar. Local legend links it to Arthurian tradition, including claims that Excalibur was cast into its waters.",
        "source": "https://en.wikipedia.org/wiki/The_Loe"
    },
    {
        "name": "Long Man of Wilmington",
        "lat": 50.81,
        "lng": 0.188,
        "category": "giant",
        "region": "Sussex",
        "summary": "The Long Man of Wilmington or Wilmington Giant is a hill figure on the steep slopes of Windover Hill near Wilmington, East Sussex, England. It is 6 miles (9.7 km) northwest of Eastbourne and 1⁄3 mile (540 m) south of Wilmington. Locally, the figure was once often called the Green Man. The Long Man is 235 feet (72 m) tall, holds two \"staves\", and is designed to look in proportion when viewed from below.",
        "source": "https://en.wikipedia.org/wiki/Long_Man_of_Wilmington"
    },
    {
        "name": "The Long Man of Wilmington",
        "lat": 50.812,
        "lng": 0.189,
        "category": "giant",
        "region": "East Sussex",
        "summary": "A giant figure carved into the chalk downs of Sussex, 69 metres tall, holding two staves. His age and meaning are unknown — possibly a Celtic deity, a Roman soldier, or a medieval pilgrim marker. He watches silently from the hillside.",
        "source": "https://en.wikipedia.org/wiki/Long_Man_of_Wilmington"
    },
    {
        "name": "Long Meg and Her Daughters",
        "lat": 54.7279,
        "lng": -2.6677,
        "category": "ancient_site",
        "region": "Cumbria",
        "summary": "A stone circle said to be a coven of witches turned to stone for dancing on the Sabbath. Long Meg herself stands apart, taller and marked with strange carvings.",
        "source": "https://en.wikipedia.org/wiki/Long_Meg_and_Her_Daughters"
    },
    {
        "name": "Longwitton Dragon",
        "lat": 55.22,
        "lng": -1.879,
        "category": "dragon",
        "region": "Northumberland",
        "summary": "A Northumbrian dragon that guarded three healing wells near Longwitton and denied villagers their water. The beast was eventually overcome by a knight who used reflection, timing, and a sharp blade.",
        "source": "https://en.wikipedia.org/wiki/Longwitton_dragon"
    },
    {
        "name": "Lugh",
        "lat": 54.003,
        "lng": -6.415,
        "category": "deity",
        "region": "Ireland & Northern Britain",
        "summary": "The shining god of skill and craftsmanship in Celtic tradition — master of every art. His festival Lughnasadh marks the first harvest. He slew the monstrous Balor of the Evil Eye with a slingshot to end a tyrannical age.",
        "source": "https://en.wikipedia.org/wiki/Lugh"
    },
    {
        "name": "Ly Erg",
        "lat": 57.0833,
        "lng": -3.6667,
        "category": "fairy",
        "region": "Scotland",
        "summary": "The Ly Erg is a fairy from Scottish folklore, particularly associated with the area in and around the Glenmore Forest, part of the present-day Cairngorms National Park. It is dressed as a soldier, distinguishable from a real soldier only by its red right hand, said to be stained with the blood of its victims. While out walking it will stop near water, and by raising its right hand challenge passersby to fight.",
        "source": "https://en.wikipedia.org/wiki/Ly_Erg"
    },
    {
        "name": "Lyonesse",
        "lat": 49.966,
        "lng": -6.321,
        "category": "location",
        "region": "Scilly Isles",
        "summary": "A drowned kingdom said to lie beneath the waves between Cornwall and the Isles of Scilly — a land of a hundred and forty churches, lost in a single night of catastrophic flooding. Tristan was born there. On still days, locals claim to hear its bells.",
        "source": "https://en.wikipedia.org/wiki/Lyonesse"
    },
    {
        "name": "Mabon ap Modron",
        "lat": 51.703,
        "lng": -2.904,
        "category": "hero",
        "region": "Wales",
        "summary": "The divine son stolen from his mother Modron when only three nights old. In Arthurian tradition, his rescue becomes one of the great mythic errands before the hunt for Twrch Trwyth.",
        "source": "https://en.wikipedia.org/wiki/Mabon_ap_Modron"
    },
    {
        "name": "Maeshowe Runes",
        "lat": 58.996,
        "lng": -3.189,
        "category": "norse",
        "region": "Orkney",
        "summary": "A Neolithic chambered cairn broken into by Norse visitors who carved runes into the stone. Ancient tomb became Viking noticeboard, proving folklore sometimes arrives with a knife and poor manners.",
        "source": "https://en.wikipedia.org/wiki/Maeshowe"
    },
    {
        "name": "Mag Lena",
        "lat": 53.29,
        "lng": -7.52,
        "category": "location",
        "region": "County Offaly",
        "summary": "Mag Lena, Mag Léna, or Mag Léne was the name of a plain or heath in the Gaelic Irish territory of Firceall, between modern Tullamore and Durrow in County Offaly. Mag Lena straddled the Esker Riada, was near the border between Mide and Laigin (Leinster), and is mentioned in Irish manuscripts as the site of several legendary, pseudohistorical, and historical events.",
        "source": "https://en.wikipedia.org/wiki/Mag_Lena"
    },
    {
        "name": "Maponos",
        "lat": 54.99,
        "lng": -3.18,
        "category": "deity",
        "region": "Northern Britain",
        "summary": "A youthful Celtic god whose name means something like divine son. He is linked to music, youth, and the Welsh figure Mabon, a child of mystery and rescue.",
        "source": "https://en.wikipedia.org/wiki/Maponos"
    },
    {
        "name": "Mari Lwyd",
        "lat": 51.48,
        "lng": -3.18,
        "category": "ritual",
        "region": "Wales",
        "summary": "A winter wassailing custom in which a decorated horse skull is carried from door to door. The party trades verses with householders before being admitted for food, drink, and seasonal chaos.",
        "source": "https://en.wikipedia.org/wiki/Mari_Lwyd"
    },
    {
        "name": "Merlin's Cave",
        "lat": 50.6683,
        "lng": -4.7594,
        "category": "location",
        "region": "Cornwall",
        "summary": "Merlin's Cave is a natural sea tunnel beneath Tintagel Castle in Cornwall, England, connecting Tintagel Haven on the east side of the island to West Cove on the west. At low tide, it is possible to walk from one entrance to the other along a sandy floor. At high tide, the tunnel becomes impassable as it fills with seawater from end to end.",
        "source": "https://en.wikipedia.org/wiki/Merlin%27s_Cave"
    },
    {
        "name": "Merlin's Oak",
        "lat": 51.8606,
        "lng": -4.2989,
        "category": "location",
        "region": "Wales",
        "summary": "Merlin's Oak, also known as the Old Oak and Priory Oak, was a pedunculate oak that once stood on the corner of Oak Lane and Priory Street in Carmarthen, South Wales. Merlin's Oak is associated with the legend of Merlin in the local lore, but it is also said to have been planted by a schoolmaster in 1659 or 1660, to celebrate the return of King Charles II of England to the throne.",
        "source": "https://en.wikipedia.org/wiki/Merlin%27s_Oak"
    },
    {
        "name": "The Merry Maidens",
        "lat": 50.065,
        "lng": -5.5897,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "The Merry Maidens, also known as Dawn's Men is a Late Neolithic stone circle located 2 miles (3 km) to the south of the village of St Buryan, in Cornwall. A pair of standing stones, The Pipers is associated both geographically and in legend.",
        "source": "https://en.wikipedia.org/wiki/The_Merry_Maidens"
    },
    {
        "name": "Metheringham Lass",
        "lat": 53.1375,
        "lng": -0.3464,
        "category": "ghost",
        "region": "RAF Metheringham",
        "summary": "The Metheringham Lass is the name given to an apparition which has been reported at RAF Metheringham.",
        "source": "https://en.wikipedia.org/wiki/Metheringham_Lass"
    },
    {
        "name": "Moel Tŷ Uchaf",
        "lat": 52.9233,
        "lng": -3.4055,
        "category": "ancient_site",
        "region": "Wales",
        "summary": "Moel Tŷ Uchaf is a stone circle near the village of Llandrillo, Denbighshire, north Wales.",
        "source": "https://en.wikipedia.org/wiki/Moel_T%C5%B7_Uchaf"
    },
    {
        "name": "Morag of Loch Morar",
        "lat": 56.964,
        "lng": -5.681,
        "category": "water",
        "region": "Highland, Scotland",
        "summary": "A serpentine creature dwelling in Loch Morar — Britain's deepest freshwater loch. Unlike Nessie, Morag is traditionally considered an omen of death for the local Macdonald clan.",
        "source": "https://en.wikipedia.org/wiki/Morag_(lake_monster)"
    },
    {
        "name": "Morgawrr",
        "lat": 50.151,
        "lng": -5.069,
        "category": "water",
        "region": "Cornwall",
        "summary": "A serpentine sea monster reported in Falmouth Bay since the 1870s. Witnesses describe a humped creature fifteen to twenty feet long, raising a small head on a long neck from the swell.",
        "source": "https://en.wikipedia.org/wiki/Morgawr"
    },
    {
        "name": "The Morrigan",
        "lat": 53.749,
        "lng": -6.497,
        "category": "deity",
        "region": "Ireland & Britain",
        "summary": "A triple goddess of war, fate and death — crow-headed, battle-hungry. She appeared to heroes before combat as an omen, sometimes aiding them, sometimes sealing their doom. Her crows still circle over ancient hillforts.",
        "source": "https://en.wikipedia.org/wiki/Morrígan"
    },
    {
        "name": "Museum of Witchcraft and Magic",
        "lat": 50.689,
        "lng": -4.692,
        "category": "location",
        "region": "Cornwall",
        "summary": "The Museum of Witchcraft and Magic, formerly known as the Museum of Witchcraft, is a museum dedicated to European witchcraft and magic located in the village of Boscastle in Cornwall, south-west England. It houses exhibits devoted to folk magic, ceremonial magic, Freemasonry, and Wicca, with its collection of such objects having been described as the largest in the world.",
        "source": "https://en.wikipedia.org/wiki/Museum_of_Witchcraft_and_Magic"
    },
    {
        "name": "Mên Scryfa",
        "lat": 50.1622,
        "lng": -5.6033,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "Mên Scryfa is an inscribed standing stone in Cornwall, England, United Kingdom. The inscription, dating to the early medieval period, commemorates \"Rialobranus son of Cunovalus.\"",
        "source": "https://en.wikipedia.org/wiki/M%C3%AAn_Scryfa"
    },
    {
        "name": "Mên-an-Tol",
        "lat": 50.1586,
        "lng": -5.6045,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "The Mên-an-Tol is a small formation of standing stones in Cornwall, United Kingdom. It is about three miles northwest of Madron. It is also known locally as the \"Crick Stone\".",
        "source": "https://en.wikipedia.org/wiki/M%C3%AAn-an-Tol"
    },
    {
        "name": "Nanny Rutt",
        "lat": 52.7485,
        "lng": -0.3792,
        "category": "beast",
        "region": "Lincolnshire",
        "summary": "Nanny Rutt is a character in a cautionary tale associated with Nanny Rutt's well, an artesian spring in Math Wood, near Northorpe, in the parish of Thurlby, Lincolnshire. The story goes that a named girl went into the wood, to the well and disappeared having been taken off by Nanny Rutt.",
        "source": "https://en.wikipedia.org/wiki/Nanny_Rutt"
    },
    {
        "name": "Nine Maidens Stone Row",
        "lat": 50.4716,
        "lng": -4.9093,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "Nine Maidens stone row is an ancient monument in the parish of St Columb Major, Cornwall, England. The Nine Maidens are also known in Cornish as Naw-voz, or Naw-whoors meaning \"the nine sisters\". This late neolithic stone row is 2 miles (3.2 km) north of St Columb Major.",
        "source": "https://en.wikipedia.org/wiki/Nine_Maidens_stone_row"
    },
    {
        "name": "Nodens",
        "lat": 51.708,
        "lng": -2.53,
        "category": "deity",
        "region": "Gloucestershire",
        "summary": "A Romano-British god of healing, hunting, dogs, and the sea, worshipped at Lydney Park. His temple complex suggests a cult of cure, dream, water, and sacred hounds.",
        "source": "https://en.wikipedia.org/wiki/Nodens"
    },
    {
        "name": "Nuckelavee",
        "lat": 58.978,
        "lng": -2.961,
        "category": "water",
        "region": "Orkney",
        "summary": "The most feared creature in Orcadian mythology — a skinless, horse-like demon from the sea. Its single eye blazes red, its black blood visible through exposed veins. It brings plague and famine.",
        "source": "https://en.wikipedia.org/wiki/Nuckelavee"
    },
    {
        "name": "Orkneyinga Saga",
        "lat": 58.984,
        "lng": -2.959,
        "category": "norse",
        "region": "Orkney & Shetland",
        "summary": "The Old Norse saga of the earls of Orkney, binding the Northern Isles to Norway, Scotland, feud, conversion, sea-kings, and bloodline memory.",
        "source": "https://en.wikipedia.org/wiki/Orkneyinga_saga"
    },
    {
        "name": "Osmington White Horse",
        "lat": 50.6574,
        "lng": -2.4044,
        "category": "ancient_site",
        "region": "Dorset",
        "summary": "The Osmington White Horse is a hill figure cut into the limestone of Osmington Hill just north of Weymouth in Dorset in 1808. It is in the South Dorset Downs in the parish of Osmington.",
        "source": "https://en.wikipedia.org/wiki/Osmington_White_Horse"
    },
    {
        "name": "Overtoun Bridge",
        "lat": 55.9526,
        "lng": -4.5252,
        "category": "location",
        "region": "Scotland",
        "summary": "Overtoun Bridge is a category B-listed structure over the Overtoun Burn on the approach road from the west to Overtoun House, near Dumbarton in West Dunbartonshire, Scotland. It was completed in 1895, based on a design by the landscape architect H. E. Milner. It spans a ditch known as Spardie Linn.",
        "source": "https://en.wikipedia.org/wiki/Overtoun_Bridge"
    },
    {
        "name": "Owlman of Mawnan",
        "lat": 50.065,
        "lng": -5.093,
        "category": "beast",
        "region": "Cornwall",
        "summary": "A huge owl-like creature with red eyes and black claws, first sighted hovering over Mawnan church tower in 1976. Multiple witnesses reported encounters over the following years.",
        "source": "https://en.wikipedia.org/wiki/Owlman"
    },
    {
        "name": "Padfoot",
        "lat": 53.8,
        "lng": -1.55,
        "category": "beast",
        "region": "Yorkshire",
        "summary": "A shaggy spectral dog said to follow travellers with soft padding steps. Like many northern black dogs, Padfoot is both warning and threat, appearing where lanes grow dark and company grows thin.",
        "source": "https://en.wikipedia.org/wiki/Black_dog_(folklore)"
    },
    {
        "name": "Pendle Witches",
        "lat": 53.87,
        "lng": -2.296,
        "category": "witch",
        "region": "Lancashire",
        "summary": "In 1612, twelve people from the Pendle Hill area were tried for witchcraft in the most significant witch trial in English history. Ten were hanged.",
        "source": "https://en.wikipedia.org/wiki/Pendle_witches"
    },
    {
        "name": "Penhale Sands",
        "lat": 50.37,
        "lng": -5.122,
        "category": "location",
        "region": "Cornwall",
        "summary": "Beneath these vast dunes lies the lost city of Langarrow, swallowed by the encroaching sands as divine punishment for the wickedness of its people. On quiet evenings, some say they can hear the muffled toll of church bells beneath the sand.",
        "source": "https://en.wikipedia.org/wiki/Penhale_Sands"
    },
    {
        "name": "The Pipers",
        "lat": 50.5155,
        "lng": -4.4599,
        "category": "ancient_site",
        "region": "Cornwall",
        "summary": "The Pipers are a pair of standing stones near The Hurlers stone circles, located on Bodmin Moor near the village of Minions, Cornwall, UK. They share the name with another pair of standing stones near the Merry Maidens to the south of the village of St Buryan, also in Cornwall.",
        "source": "https://en.wikipedia.org/wiki/The_Pipers"
    },
    {
        "name": "Piskie",
        "lat": 50.266,
        "lng": -5.052,
        "category": "fairy",
        "region": "Cornwall & Devon",
        "summary": "Small West Country fae known for leading travellers astray, especially on moors and lanes. To be 'piskie-led' is to wander in circles while the familiar world quietly rearranges itself.",
        "source": "https://en.wikipedia.org/wiki/Pixie"
    },
    {
        "name": "Porlock Stone Circle",
        "lat": 51.1895,
        "lng": -3.654,
        "category": "ancient_site",
        "region": "Somerset",
        "summary": "A small Exmoor stone circle whose weathered stones sit in a landscape of moorland lore. Its current 'Ireland' label was a scrape error; this belongs firmly to Somerset.",
        "source": "https://en.wikipedia.org/wiki/Porlock_Stone_Circle"
    },
    {
        "name": "Puck",
        "lat": 50.982,
        "lng": 0.218,
        "category": "fairy",
        "region": "East Sussex",
        "summary": "The oldest Old Thing in England — an ancient spirit of place tied to the Sussex Weald, known since before the Normans came. Rudyard Kipling immortalised him as the guardian of England's deep memory.",
        "source": "https://en.wikipedia.org/wiki/Puck_(mythology)"
    },
    {
        "name": "The Ratman of Southend",
        "lat": 51.5412,
        "lng": 0.711,
        "category": "ghost",
        "region": "Essex",
        "summary": "The Ratman of Southend is an English urban legend originating in Southend-on-Sea, Essex.\nThe story of the Ratman tells of an old homeless man, who while seeking shelter from the cold in an underpass, was set upon by a group of youths and beaten to near-death. The cold and blood loss finished his life. As he died, the numerous vermin who inhabit the area gathered, and were found to have devoured his face.",
        "source": "https://en.wikipedia.org/wiki/The_Ratman_of_Southend"
    },
    {
        "name": "Red Horse of Tysoe",
        "lat": 52.1012,
        "lng": -1.4839,
        "category": "ancient_site",
        "region": "South Warwickshire",
        "summary": "\nThe Red Horse of Tysoe was a hill figure in the parish of Tysoe, South Warwickshire, England, cut into the red clay below the escarpment of Edgehill. It gave its name to the surrounding area, which is still known as the Vale of Red Horse or Red Horse Vale. The figure was first recorded in 1607, and in its earliest form was nearly 100 yards long.",
        "source": "https://en.wikipedia.org/wiki/Red_Horse_of_Tysoe"
    },
    {
        "name": "Redcap",
        "lat": 55.649,
        "lng": -2.348,
        "category": "beast",
        "region": "Scottish Borders",
        "summary": "A murderous goblin dwelling in ruined border castles, who dyes his cap with the blood of travellers he has slain. He must kill regularly or die himself. Iron repels him; scripture makes him flee.",
        "source": "https://en.wikipedia.org/wiki/Redcap"
    },
    {
        "name": "Rhiannon",
        "lat": 52.016,
        "lng": -4.466,
        "category": "deity",
        "region": "Wales",
        "summary": "A major figure of Welsh mythology associated with horses, sovereignty, endurance, and otherworldly radiance. She first appears riding calmly beyond mortal pursuit, impossible to catch unless asked to stop.",
        "source": "https://en.wikipedia.org/wiki/Rhiannon"
    },
    {
        "name": "Rhitta Gawr",
        "lat": 53.068,
        "lng": -4.076,
        "category": "hero",
        "region": "Snowdonia, Wales",
        "summary": "The great giant-king of Wales who made a cloak from the beards of the kings he slew. He demanded Arthur's beard for the final trim. Arthur refused — and killed him on the slopes of Snowdon, which was then called Rhitta's Cairn.",
        "source": "https://en.wikipedia.org/wiki/Rhitta_Gawr"
    },
    {
        "name": "Robin Goodfellow",
        "lat": 52.0,
        "lng": -1.0,
        "category": "fairy",
        "region": "England",
        "summary": "A puckish household and woodland spirit, prankster, shape-shifter, and night-wanderer. Robin Goodfellow links older English fairy belief to the literary Puck of Shakespeare and Kipling.",
        "source": "https://en.wikipedia.org/wiki/Puck_(folklore)"
    },
    {
        "name": "Rollright Stones curse",
        "lat": 51.975,
        "lng": -1.571,
        "category": "ancient_site",
        "region": "Oxfordshire",
        "summary": "A Bronze Age stone circle said to be a king and his knights turned to stone by a witch. The stones are impossible to count twice and reach the same number. The King Stone bleeds if cut.",
        "source": "https://en.wikipedia.org/wiki/Rollright_Stones"
    },
    {
        "name": "Rudston Monolith",
        "lat": 54.094,
        "lng": -0.323,
        "category": "ancient_site",
        "region": "East Yorkshire",
        "summary": "The tallest standing stone in Britain, rising from a churchyard like a leftover sentence from an older religion. Its original purpose is unknown, which leaves folklore plenty of room to breathe.",
        "source": "https://en.wikipedia.org/wiki/Rudston_Monolith"
    },
    {
        "name": "Sarah Whitehead",
        "lat": 51.5142,
        "lng": -0.0885,
        "category": "ghost",
        "region": "London",
        "summary": "Sarah Whitehead is the reported name of a woman whose ghost is said to haunt the Bank of England; her ghost became known as The Black Nun.",
        "source": "https://en.wikipedia.org/wiki/Sarah_Whitehead"
    },
    {
        "name": "Sea Mither",
        "lat": 58.984,
        "lng": -2.959,
        "category": "deity",
        "region": "Orkney",
        "summary": "An Orcadian summer sea-spirit who calms the waters and restrains the monstrous Teran. Her yearly struggle with him explains the turn between gentle seas and winter storms.",
        "source": "https://en.wikipedia.org/wiki/Sea_Mither"
    },
    {
        "name": "Selkies of Orkney",
        "lat": 59.003,
        "lng": -3.213,
        "category": "water",
        "region": "Orkney",
        "summary": "Seal-folk who shed their skins to walk as humans on land. If a fisherman steals a selkie's skin, she cannot return to the sea and must live as his wife — yearning always for the ocean.",
        "source": "https://en.wikipedia.org/wiki/Selkie"
    },
    {
        "name": "Shellycoat",
        "lat": 55.864,
        "lng": -4.251,
        "category": "fairy",
        "region": "Lowland Scotland",
        "summary": "A Scottish bogle draped in shells that rattle with every movement. It haunts streams and rivers, delighting in leading travellers astray with mischievous cries.",
        "source": "https://en.wikipedia.org/wiki/Shellycoat"
    },
    {
        "name": "Shug Monkey",
        "lat": 52.1441,
        "lng": 0.3333,
        "category": "beast",
        "region": "Cambridgeshire",
        "summary": "\nIn the folklore of Cambridgeshire, the Shug Monkey is a creature that shares features of a dog and monkey, which reportedly haunted Slough Hill Lane. The creature, believed to have the body of a jet-black shaggy sheepdog and the face of a monkey with staring eyes, was believed to be a supernatural ghost or demon.",
        "source": "https://en.wikipedia.org/wiki/Shug_Monkey"
    },
    {
        "name": "Simonside Dwarfs",
        "lat": 55.304,
        "lng": -1.98,
        "category": "fairy",
        "region": "Northumberland",
        "summary": "Dwarf-like beings said to lure night travellers across the Simonside Hills with false lights. Follow them too far and the moor becomes a trap with no ordinary road home.",
        "source": "https://en.wikipedia.org/wiki/Simonside_Dwarfs"
    },
    {
        "name": "Sockburn Worm",
        "lat": 54.489,
        "lng": -1.467,
        "category": "dragon",
        "region": "County Durham",
        "summary": "A dragon or wyrm slain by Sir John Conyers near Sockburn on the River Tees. The Conyers falchion, said to be the weapon used, became part of local ceremonial tradition.",
        "source": "https://en.wikipedia.org/wiki/Sockburn_Worm"
    },
    {
        "name": "Spectre of Newby Church",
        "lat": 54.108,
        "lng": -1.449,
        "category": "ghost",
        "region": "Yorkshire",
        "summary": "The Spectre of Newby Church is the name given to a figure found in a photograph taken in the Church of Christ the Consoler, on the grounds of Newby Hall in North Yorkshire, England, United Kingdom. The image was taken in 1963 by the Reverend Kenneth F. Lord.",
        "source": "https://en.wikipedia.org/wiki/Spectre_of_Newby_Church"
    },
    {
        "name": "Spong Hill",
        "lat": 52.737,
        "lng": 0.934,
        "category": "location",
        "region": "Norfolk",
        "summary": "Spong Hill is an Anglo-Saxon cemetery site located south of North Elmham in Norfolk, England. It is the largest known Early Anglo-Saxon cremation site. The site consists of a large cremation cemetery and a smaller, 6th-century burial cemetery of 57 inhumations. Several of the inhumation graves were covered by small barrows and others were marked by the use of coffins.",
        "source": "https://en.wikipedia.org/wiki/Spong_Hill"
    },
    {
        "name": "Spriggan",
        "lat": 50.119,
        "lng": -5.537,
        "category": "fairy",
        "region": "Cornwall",
        "summary": "Ugly, fierce Cornish fae said to guard buried treasure, ruins, and ancient places. Though small at first glance, spriggans can swell into giant forms when angered.",
        "source": "https://en.wikipedia.org/wiki/Spriggan"
    },
    {
        "name": "Spring-Heeled Jack",
        "lat": 51.507,
        "lng": -0.127,
        "category": "ghost",
        "region": "London",
        "summary": "A terrifying figure who stalked Victorian London with eyes like burning coals. He could leap over rooftops, breathe blue flame, and vanished whenever cornered. Never caught. Never explained.",
        "source": "https://en.wikipedia.org/wiki/Spring-heeled_Jack"
    },
    {
        "name": "St Davids Cathedral",
        "lat": 51.8819,
        "lng": -5.2683,
        "category": "location",
        "region": "Wales",
        "summary": "St Davids Cathedral is a Church in Wales cathedral situated in St Davids, Britain's smallest city, in the county of Pembrokeshire, near the most westerly point of Wales.",
        "source": "https://en.wikipedia.org/wiki/St_Davids_Cathedral"
    },
    {
        "name": "St Leonard's Forest Dragons",
        "lat": 51.047,
        "lng": -0.267,
        "category": "dragon",
        "region": "West Sussex",
        "summary": "A Sussex forest once reputed to harbour dragons and serpents. Medieval and early modern stories gave the woods a scaled population, making every rustle beneath the trees sound more interesting.",
        "source": "https://en.wikipedia.org/wiki/St_Leonard%27s_Forest"
    },
    {
        "name": "St Trinian's Church",
        "lat": 54.1902,
        "lng": -4.5799,
        "category": "location",
        "region": "Isle of Man",
        "summary": "St Trinian's Church is the roofless ruin of a small chapel at the foot of Greeba Mountain, adjacent to the main A1 Douglas - Peel Road in the parish of Marown, Isle of Man. Referred to in the Manx language as a \"Keeil Brisht\", the church is the source of an ancient Manx folk tale concerning the Buggane, a huge mythical ogre who lived on Greeba Mountain and who vowed that the church should never be completed.",
        "source": "https://en.wikipedia.org/wiki/St_Trinian%27s_Church"
    },
    {
        "name": "Stanton Drew Stone Circles",
        "lat": 51.3671,
        "lng": -2.576,
        "category": "ancient_site",
        "region": "Somerset",
        "summary": "The Stanton Drew stone circles are just outside the village of Stanton Drew in the English county of Somerset. The largest stone circle is the Great Circle, 113 metres (371 ft) in diameter and the second largest stone circle in Britain ; it is considered to be one of the largest Neolithic monuments to have been built.",
        "source": "https://en.wikipedia.org/wiki/Stanton_Drew_stone_circles"
    },
    {
        "name": "Stonehenge",
        "lat": 51.179,
        "lng": -1.826,
        "category": "ancient_site",
        "region": "Wiltshire",
        "summary": "Raised by giants according to Geoffrey of Monmouth, or conjured by Merlin from Ireland — Stonehenge defies rational explanation. For five thousand years it has aligned with the solstice sun. Druids still gather here at midsummer.",
        "source": "https://en.wikipedia.org/wiki/Stonehenge"
    },
    {
        "name": "Stoor Worm",
        "lat": 58.639,
        "lng": -3.07,
        "category": "dragon",
        "region": "Caithness, Scotland",
        "summary": "The greatest of all sea serpents in Scottish legend, so vast its body encircled the earth. When the hero Assipattle slew it, its teeth became the Orkney islands and its coiled body became Iceland.",
        "source": "https://en.wikipedia.org/wiki/Stoor_Worm"
    },
    {
        "name": "Sulis",
        "lat": 51.381,
        "lng": -2.36,
        "category": "deity",
        "region": "Bath, Somerset",
        "summary": "A Celtic goddess of healing waters whose sacred spring at Bath was so powerful the Romans built a great temple around it, naming her Sulis Minerva. Thousands of curse tablets were cast into her waters — prayers, pleas and vengeance.",
        "source": "https://en.wikipedia.org/wiki/Sulis"
    },
    {
        "name": "Sutton Hoo",
        "lat": 52.0897,
        "lng": 1.3389,
        "category": "ancient_site",
        "region": "Suffolk",
        "summary": "Sutton Hoo is the site of two Anglo-Saxon cemeteries dating from the 6th to 7th centuries near Woodbridge, Suffolk, England. Archaeologists have been excavating the area since 1938, when an undisturbed ship burial containing a wealth of Anglo-Saxon artifacts was discovered.",
        "source": "https://en.wikipedia.org/wiki/Sutton_Hoo"
    },
    {
        "name": "Taranis",
        "lat": 53.465,
        "lng": -2.234,
        "category": "deity",
        "region": "Northern England",
        "summary": "The Celtic god of thunder, his wheel-symbol found carved across Roman Britain from Chester to Hadrian's Wall. Like Jupiter but wilder — his rumbling marked the turning of fate. Worshipped with fire and offering.",
        "source": "https://en.wikipedia.org/wiki/Taranis"
    },
    {
        "name": "Teran",
        "lat": 58.984,
        "lng": -2.959,
        "category": "deity",
        "region": "Orkney",
        "summary": "The winter sea-spirit of Orkney, enemy of the Sea Mither. When Teran rules, storms rise, waters turn dangerous, and the ocean remembers its teeth.",
        "source": "https://en.wikipedia.org/wiki/Teran"
    },
    {
        "name": "Thornton Road poltergeist claim",
        "lat": 52.49,
        "lng": -1.83,
        "category": "ghost",
        "region": "Britain",
        "summary": "The Thornton Road Poltergeist refers to stone-throwing incidents in a residential area of Birmingham, England, in 1981 and the subsequent police investigation.",
        "source": "https://en.wikipedia.org/wiki/Thornton_Road_poltergeist_claim"
    },
    {
        "name": "Thunor",
        "lat": 51.55,
        "lng": 0.605,
        "category": "deity",
        "region": "Anglo-Saxon England",
        "summary": "The Anglo-Saxon thunder god, cognate with Norse Thor. His name echoes in Thursday and in place-names, a hammer-crack of pre-Christian belief beneath later England.",
        "source": "https://en.wikipedia.org/wiki/Thor"
    },
    {
        "name": "Tiddy Mun",
        "lat": 53.508,
        "lng": -0.726,
        "category": "fairy",
        "region": "Lincolnshire",
        "summary": "A small shaggy spirit of the Lincolnshire marshes who controlled the fenland floods. When the land was drained, he brought sickness until appeased by offerings.",
        "source": "https://en.wikipedia.org/wiki/Tiddy_Mun"
    },
    {
        "name": "Tintagel",
        "lat": 50.668,
        "lng": -4.758,
        "category": "location",
        "region": "Cornwall",
        "summary": "The Cornish village inseparable from Arthurian legend, Merlin's sea-cave, and the ruined headland castle where medieval writers placed Arthur's conception.",
        "source": "https://en.wikipedia.org/wiki/Tintagel_Castle"
    },
    {
        "name": "Tintagel Castle",
        "lat": 50.668,
        "lng": -4.7599,
        "category": "location",
        "region": "Cornwall",
        "summary": "A cliff-edge stronghold made famous by Geoffrey of Monmouth as the place of Arthur's conception. Its sea-cut ruins keep Arthurian legend pinned to the Cornish coast.",
        "source": "https://en.wikipedia.org/wiki/Tintagel_Castle"
    },
    {
        "name": "The Towans",
        "lat": 50.2105,
        "lng": -5.4077,
        "category": "location",
        "region": "Cornwall",
        "summary": "A dune landscape in Cornwall associated with shifting sands, lost paths, and buried traces of earlier settlements. It sits within the same legendary coastline as Lyonesse and drowned church-bell tales.",
        "source": "https://en.wikipedia.org/wiki/The_Towans"
    },
    {
        "name": "Towednack",
        "lat": 50.191,
        "lng": -5.52,
        "category": "beast",
        "region": "Cornwall",
        "summary": "A Cornish parish rich in tales of piskies, saints, and old stone-country spirits. Its church and surrounding moorland belong to the strange magical geography of West Penwith.",
        "source": "https://en.wikipedia.org/wiki/Towednack"
    },
    {
        "name": "Trow",
        "lat": 60.155,
        "lng": -1.145,
        "category": "norse",
        "region": "Shetland & Orkney",
        "summary": "A small, troll-like being from Shetland and Orkney folklore, rooted in Norse tradition. Trows live in mounds, dislike sunlight, love music, and are always one bad bargain away.",
        "source": "https://en.wikipedia.org/wiki/Trow_(folklore)"
    },
    {
        "name": "Twelve Apostles, West Yorkshire",
        "lat": 53.9016,
        "lng": -1.8095,
        "category": "ancient_site",
        "region": "Yorkshire",
        "summary": "The Twelve Apostles is a stone circle near Ilkley and Burley in Wharfedale in West Yorkshire, England.",
        "source": "https://en.wikipedia.org/wiki/Twelve_Apostles%2C_West_Yorkshire"
    },
    {
        "name": "Uffington White Horse",
        "lat": 51.577,
        "lng": -1.566,
        "category": "ancient_site",
        "region": "Oxfordshire",
        "summary": "A huge prehistoric chalk horse cut into the Berkshire Downs. It watches over Dragon Hill, Wayland's Smithy, and a landscape where pagan monument, saint legend, and heroic folklore overlap.",
        "source": "https://en.wikipedia.org/wiki/Uffington_White_Horse"
    },
    {
        "name": "Up Helly Aa",
        "lat": 60.155,
        "lng": -1.145,
        "category": "ritual",
        "region": "Shetland",
        "summary": "A modern Shetland fire festival rooted in local identity and Norse revival imagery. Torch-bearing squads process through winter darkness before burning a Viking-style galley.",
        "source": "https://en.wikipedia.org/wiki/Up_Helly_Aa"
    },
    {
        "name": "Watlington White Mark",
        "lat": 51.639,
        "lng": -0.9897,
        "category": "ancient_site",
        "region": "Oxfordshire",
        "summary": "Watlington White Mark is a chalk hill figure located on Watlington Hill, a mile from the village of Watlington, Oxfordshire. It is 270 feet tall and 36 feet wide, and is one of several hill figures cut into the Chilterns, alongside the Whiteleaf Cross, Bledlow Cross and Whipsnade White Lion. The site is owned by the National Trust.",
        "source": "https://en.wikipedia.org/wiki/Watlington_White_Mark"
    },
    {
        "name": "Waun Mawn",
        "lat": 51.9716,
        "lng": -4.7912,
        "category": "ancient_site",
        "region": "Wales",
        "summary": "Waun Mawn is a megalithic site in the Preseli Mountains of Pembrokeshire, Wales. Following excavations in 2018, it became the site of a supposed dismantled Neolithic stone circle. The diameter of the postulated circle was estimated to be 110 m (360 ft), making it the fifth largest diameter for a British stone circle, after Avebury, Stanton Drew, Karl Lofts, Long Meg, and slightly larger than the Ring of Brodgar.",
        "source": "https://en.wikipedia.org/wiki/Waun_Mawn"
    },
    {
        "name": "Wayland the Smith",
        "lat": 51.567,
        "lng": -1.596,
        "category": "hero",
        "region": "Oxfordshire",
        "summary": "A legendary smith from Germanic tradition, bound to the Neolithic tomb called Wayland's Smithy. Leave a coin and an unshod horse overnight, legend says, and invisible hands may shoe it.",
        "source": "https://en.wikipedia.org/wiki/Wayland_the_Smith"
    },
    {
        "name": "Wayland's Smithy",
        "lat": 51.567,
        "lng": -1.596,
        "category": "ancient_site",
        "region": "Oxfordshire",
        "summary": "A Neolithic chambered tomb later claimed by folklore as the forge of Wayland the Smith. It is a perfect example of old stone becoming older story.",
        "source": "https://en.wikipedia.org/wiki/Wayland%27s_Smithy"
    },
    {
        "name": "Whetstones",
        "lat": 52.5711,
        "lng": -3.028,
        "category": "ancient_site",
        "region": "Wales",
        "summary": "The Whetstones are, or were, a stone circle beneath Corndon Hill in the parish of Church Stoke, Montgomeryshire, Wales, near the border with Shropshire, England. They lie immediately to the west of the village of White Grit and close to Priestweston. The site is also a short distance from the better-known Hoarstones and Mitchell's Fold circles.",
        "source": "https://en.wikipedia.org/wiki/Whetstones_%28stone_circle%29"
    },
    {
        "name": "Whiteleaf Cross",
        "lat": 51.7287,
        "lng": -0.8115,
        "category": "ancient_site",
        "region": "Buckinghamshire",
        "summary": "Whiteleaf Cross is a cross-shaped chalk hill carving, with a triangular base, on Whiteleaf Hill in Whiteleaf near Princes Risborough in Buckinghamshire.",
        "source": "https://en.wikipedia.org/wiki/Whiteleaf_Cross"
    },
    {
        "name": "The Wild Hunt",
        "lat": 53.96,
        "lng": -1.086,
        "category": "ghost",
        "region": "North Yorkshire",
        "summary": "A host of spectral huntsmen and howling hounds tearing across the winter sky. To witness the Hunt is to receive a portent of war, plague, or the death of a king.",
        "source": "https://en.wikipedia.org/wiki/Wild_Hunt"
    },
    {
        "name": "Will-o'-the-Wisp",
        "lat": 52.558,
        "lng": 0.163,
        "category": "fairy",
        "region": "The Fens, Cambridgeshire",
        "summary": "Flickering phosphorescent lights seen drifting over the marshes and fens. Believed to be mischievous spirits luring travellers off safe paths into treacherous bogs.",
        "source": "https://en.wikipedia.org/wiki/Will-o%27-the-wisp"
    },
    {
        "name": "Witches' Well",
        "lat": 55.9489,
        "lng": -3.1964,
        "category": "witch",
        "region": "Edinburgh",
        "summary": "The Witches' Well is a monument to accused witches burned at the stake in Edinburgh, Scotland, and is the only one of its kind in the city.",
        "source": "https://en.wikipedia.org/wiki/Witches%27_Well%2C_Edinburgh"
    },
    {
        "name": "Witchknowe Park",
        "lat": 56.0253,
        "lng": -3.4027,
        "category": "location",
        "region": "Fife",
        "summary": "Witchknowe Park is a park and historic site in Inverkeithing in Fife, Scotland.",
        "source": "https://en.wikipedia.org/wiki/Witchknowe_Park"
    },
    {
        "name": "Withypool Stone Circle",
        "lat": 51.0963,
        "lng": -3.6604,
        "category": "ancient_site",
        "region": "Somerset",
        "summary": "Withypool Stone Circle, also known as Withypool Hill Stone Circle, is a stone circle located on the Exmoor moorland, near the village of Withypool in the southwestern English county of Somerset. The ring is part of a tradition of stone circle construction that spread throughout much of Britain, Ireland, and Brittany during the Late Neolithic and Early Bronze Age, over a period between 3300 and 900 BCE.",
        "source": "https://en.wikipedia.org/wiki/Withypool_Stone_Circle"
    },
    {
        "name": "Woden",
        "lat": 52.585,
        "lng": -2.125,
        "category": "deity",
        "region": "Anglo-Saxon England",
        "summary": "The Anglo-Saxon form of Odin, remembered in royal genealogies, place-names, and Wednesday. He stands where god, ancestor, wanderer, and war-lord blur into one shadowed figure.",
        "source": "https://en.wikipedia.org/wiki/Woden"
    },
    {
        "name": "Worm of Linton",
        "lat": 55.521,
        "lng": -2.394,
        "category": "dragon",
        "region": "Scottish Borders",
        "summary": "A venomous border worm that laired in a hollow near Linton, poisoning the countryside with its breath. Somerville of Lariston slew it with a lance tipped by a burning peat or wheel of pitch.",
        "source": "https://en.wikipedia.org/wiki/Worm_of_Linton"
    },
    {
        "name": "Wulver",
        "lat": 60.333,
        "lng": -1.333,
        "category": "beast",
        "region": "Shetland",
        "summary": "A gentle wolf-headed man of Shetland folklore, unlike ordinary werewolf tales. The Wulver fishes alone and is said to leave food for poor families on windowsills.",
        "source": "https://en.wikipedia.org/wiki/Wulver"
    },
    {
        "name": "Y Ddraig Goch",
        "lat": 53.219,
        "lng": -4.091,
        "category": "dragon",
        "region": "Snowdonia, Wales",
        "summary": "The Red Dragon of Wales, buried beneath Dinas Emrys, locked in eternal battle with a white dragon. The young Merlin prophesied that the red dragon — the true Britons — would ultimately prevail.",
        "source": "https://en.wikipedia.org/wiki/Y_Ddraig_Goch"
    },
    {
        "name": "Yester Castle",
        "lat": 55.8906,
        "lng": -2.7105,
        "category": "location",
        "region": "Scotland",
        "summary": "A ruined East Lothian castle famed for the Goblin Ha', an underground vaulted chamber said to have been built by magical arts for the wizard-like Hugo de Giffard.",
        "source": "https://en.wikipedia.org/wiki/Yester_Castle"
    },
    {
        "name": "Zennor",
        "lat": 50.192,
        "lng": -5.568,
        "category": "location",
        "region": "Cornwall",
        "summary": "Zennor is a village and civil parish in Cornwall, England, United Kingdom. The parish includes the villages of Zennor, Boswednack and Porthmeor and the hamlet of Treen. Zennor lies on the north coast, about 6 miles (10 km) north of Penzance, along the B3306 road which connects St Ives to the A30 road. Alphabetically, the parish is the last in Britain. Its name comes from the Cornish name for the local saint, Saint Senara.",
        "source": "https://en.wikipedia.org/wiki/Zennor"
    },
    {
        "name": "Black Annis",
        "lat": 52.638, "lng": -1.152,
        "category": "beast",
        "region": "Leicestershire",
        "summary": "A blue-faced hag with iron claws who dwelt in a cave she carved from the sandstone of the Dane Hills near Leicester. She crouched in her oak tree waiting to snatch children and lambs, tanning their skins to wear around her waist. Cottages in Leicestershire were built with small windows to keep her out.",
        "source": "https://en.wikipedia.org/wiki/Black_Annis"
    },
    {
        "name": "Wisht Hounds",
        "lat": 50.574, "lng": -3.914,
        "category": "beast",
        "region": "Dartmoor, Devon",
        "summary": "The spectral pack that hunts across Dartmoor on wild nights, led by Dewer the huntsman or the Devil himself. Their baying chills the blood and to be caught in their path is death. They are kennelled beneath Wistman\'s Wood, where the ancient oaks grow twisted and low.",
        "source": "https://en.wikipedia.org/wiki/Wisht_Hounds"
    },
    {
        "name": "Awd Goggie",
        "lat": 53.958, "lng": -1.082,
        "category": "beast",
        "region": "Yorkshire",
        "summary": "A boggart-like spirit lurking in orchards and gooseberry bushes across Yorkshire, set to guard the ripening fruit from children. Its rustling presence in the leaves was enough to keep small hands at bay — whether it was real or merely a parents\' invention, none could say for certain.",
        "source": "https://en.wikipedia.org/wiki/Awd_Goggie"
    },
    {
        "name": "Gurt Worm",
        "lat": 51.108, "lng": -3.002,
        "category": "dragon",
        "region": "Somerset",
        "summary": "A great serpent said to have terrorised the villages of the Quantock Hills, coiling itself around fields and devouring cattle. A local hero eventually slew it, but not before the creature\'s death throes carved the valleys of the hills. Its memory persists in the landscape itself.",
        "source": "https://en.wikipedia.org/wiki/Gurt_Worm"
    },
    {
        "name": "Filey Dragon",
        "lat": 54.212, "lng": -0.269,
        "category": "dragon",
        "region": "North Yorkshire",
        "summary": "A fearsome dragon that made its lair in the tidal gully of Filey Brigg. The townsfolk defeated it by luring it to eat so much sticky parkin cake that its jaws seized shut and it plunged into the sea to drown. The jagged rocks of the Brigg are said to be its bones, jutting into the North Sea still.",
        "source": "https://en.wikipedia.org/wiki/Filey_Brigg"
    },
    {
        "name": "Hagg Worm",
        "lat": 54.433, "lng": -0.807,
        "category": "dragon",
        "region": "North Yorkshire Moors",
        "summary": "A venomous serpent of the North Yorkshire moors, lurking in the deep wooded gullies called haggs. One of several worms said to have plagued the region before the age of saints and knights, giving the landscape both its name and its dread.",
        "source": "https://en.wikipedia.org/wiki/Worm_(mythology)"
    },
    {
        "name": "Renwick Cockatrice",
        "lat": 54.738, "lng": -2.551,
        "category": "beast",
        "region": "Cumbria",
        "summary": "When workmen demolished the old church at Renwick in 1733, a great winged creature flew out from the foundations — a cockatrice hatched from the ancient stonework. John Tallantire beat it to death with a branch of rowan, the only wood proof against its deadly gaze. The church was rebuilt, but the rowan was kept.",
        "source": "https://en.wikipedia.org/wiki/Renwick_Cockatrice"
    },
    {
        "name": "Fad Felen",
        "lat": 51.700, "lng": -3.388,
        "category": "beast",
        "region": "Glamorgan, Wales",
        "summary": "The Yellow Plague — a monstrous creature of Welsh legend whose breath carried pestilence across the land. Said to take the form of a great serpent or a yellow mist rolling off the mountains, it features in tales of St Teilo who fled its devastation across the sea to Brittany.",
        "source": "https://en.wikipedia.org/wiki/Fad_Felen"
    },
    {
        "name": "Bomere Fish",
        "lat": 52.700, "lng": -2.762,
        "category": "water",
        "region": "Shropshire",
        "summary": "A great pike of monstrous size said to inhabit Bomere Pool near Shrewsbury, guardian of a drowned village said to lie beneath its waters. The fish surfaces only to herald disaster for the local gentry — and the pool has a dark reputation that survives to this day.",
        "source": "https://en.wikipedia.org/wiki/Bomere_Pool"
    },
    {
        "name": "Hyter Sprite",
        "lat": 52.450, "lng": 1.350,
        "category": "fairy",
        "region": "East Anglia",
        "summary": "A shape-shifting spirit of the East Anglian fens, capable of taking the form of a sand martin. Hyter sprites could restore lost children to their families — or lead them deeper into the marshes, depending on their mood. They are among the rarer friendly fae of English folklore.",
        "source": "https://en.wikipedia.org/wiki/Hyter_Sprite"
    },
    {
        "name": "Lantern Man",
        "lat": 52.520, "lng": 1.250,
        "category": "ghost",
        "region": "Norfolk",
        "summary": "A malevolent will-o-the-wisp of the Norfolk Broads, more dangerous than most — it actively pursues lone travellers across the marshes. Whistling or swearing at it only makes it angrier. The only escape is to throw yourself face down in the mud and wait for it to pass.",
        "source": "https://en.wikipedia.org/wiki/Lantern_Man"
    },
    {
        "name": "Penhill Giant",
        "lat": 54.285, "lng": -1.895,
        "category": "giant",
        "region": "North Yorkshire",
        "summary": "A giant said to have haunted Penhill in Wensleydale, keeping a pack of hounds that terrorised the shepherds of the dale. A local hermit eventually brought about his downfall. His hill-top eyrie commands the whole of Wensleydale — a landscape that still feels watched from above.",
        "source": "https://en.wikipedia.org/wiki/Penhill"
    },
    {
        "name": "Old Cockern",
        "lat": 50.583, "lng": -3.919,
        "category": "ghost",
        "region": "Dartmoor, Devon",
        "summary": "The spectral huntsman of Dartmoor, keeper of the Wisht Hounds, who rides out on stormy nights to gather the souls of the unbaptised. He is sometimes identified with the Devil, sometimes with an ancient moorland spirit older than Christianity. Farmers left offerings on the moor to keep him from their doors.",
        "source": "https://en.wikipedia.org/wiki/Wild_Hunt"
    },
    {
        "name": "Mersey Mermaid",
        "lat": 53.400, "lng": -3.000,
        "category": "water",
        "region": "Merseyside",
        "summary": "A mermaid sighted in the Mersey estuary and along the Lancashire and Cheshire coast. Her appearance traditionally foretold storms, floods, or disaster for the port towns along the river — a warning from the deep that sailors had learned to heed.",
        "source": "https://en.wikipedia.org/wiki/Mermaid"
    },
    {
        "name": "Mordiford Dragon",
        "lat": 52.043, "lng": -2.638,
        "category": "dragon",
        "region": "Herefordshire",
        "summary": "A young girl named Maud found a tiny green serpent near Mordiford and kept it as a pet, feeding it milk. It grew into a vast dragon and began devouring cattle — then people. A condemned prisoner finally slew it from a barrel near the river, killing the beast but dying himself from its poisoned breath.",
        "source": "https://en.wikipedia.org/wiki/Dragon_of_Mordiford"
    },
    {
        "name": "Thanet Sea Monster",
        "lat": 51.358, "lng": 1.395,
        "category": "water",
        "region": "Kent",
        "summary": "A vast sea creature reported off the Isle of Thanet at various points in history, its silhouette glimpsed through sea mist by fishermen. The waters around Thanet have a dark reputation — the isle was once separated from mainland Kent by the Wantsum Channel, and old stories speak of things that came through it.",
        "source": "https://en.wikipedia.org/wiki/Isle_of_Thanet"
    },
    {
        "name": "Stratford Lion",
        "lat": 52.192, "lng": -1.708,
        "category": "beast",
        "region": "Warwickshire",
        "summary": "A spectral lion said to haunt the roads around Stratford-upon-Avon — silent, luminous-eyed, always seen alone on the road at night. Unlike the great black dogs of other counties, this phantom takes the form of a big cat, one of England\'s stranger and more localised legends.",
        "source": "https://en.wikipedia.org/wiki/Phantom_cat"
    },
    {
        "name": "Veasta",
        "lat": 59.150, "lng": -2.773,
        "category": "water",
        "region": "Orkney",
        "summary": "A sea beast of Orcadian waters, seen offshore during storms in old accounts. Like many Norse-influenced sea legends of Orkney, Veasta sits between monster and natural phenomenon — a reminder that the sea around these islands has always been treated as a living, sentient thing.",
        "source": "https://en.wikipedia.org/wiki/Veasta"
    },
    {
        "name": "Yallery Brown",
        "lat": 53.508, "lng": -0.560,
        "category": "fairy",
        "region": "Lincolnshire",
        "summary": "A tiny, wizened creature with yellow-brown skin found pinned beneath a flat stone in the Lincolnshire fens. When freed, he offered to help with a young labourer\'s work — but warned never to be thanked. The man thanked him. From that day, everything he touched went wrong.",
        "source": "https://en.wikipedia.org/wiki/Yallery_Brown"
    },
    {
        "name": "Seelie Court",
        "lat": 56.324, "lng": -3.003,
        "category": "fairy",
        "region": "Scotland",
        "summary": "The blessed court of Scottish fairy tradition — benevolent fae who sometimes aided humans, but whose goodwill was never entirely safe. They moved between their twilight realm and the mortal world at the turning of the seasons, and to encounter them was to stand on the edge between fortune and ruin.",
        "source": "https://en.wikipedia.org/wiki/Seelie_court"
    },
    {
        "name": "Unseelie Court",
        "lat": 55.864, "lng": -3.232,
        "category": "fairy",
        "region": "Scotland",
        "summary": "The dark host of Scottish fairy lore — malevolent fae who needed no reason to harm mortals. They flew through the winter night as the Sluagh, pelting travellers with fairy shot. No offering could appease them. They are the reason you do not go out alone after dark in the Lowlands.",
        "source": "https://en.wikipedia.org/wiki/Unseelie_Court"
    },
    {
        "name": "Tylwyth Teg",
        "lat": 52.130, "lng": -3.783,
        "category": "fairy",
        "region": "Wales",
        "summary": "The Fair Family of Welsh folklore — beautiful golden-haired fae who danced on moonlit hills and beneath lake surfaces. They stole human children and left changelings in their place. To see them was magical; to follow them was to lose days, years, or your mind entirely.",
        "source": "https://en.wikipedia.org/wiki/Tylwyth_Teg"
    },
    {
        "name": "Aos Sí",
        "lat": 53.327, "lng": -6.248,
        "category": "fairy",
        "region": "Ireland & Scotland",
        "summary": "The people of the mounds — an ancient supernatural race who retreated into the hollow hills when the Gaels conquered Ireland. They inhabit the fairy forts and ring barrows of the landscape. To disturb their homes brings ruin. To be taken by them is to never fully return.",
        "source": "https://en.wikipedia.org/wiki/Aos_Sí"
    },
    {
        "name": "Glaistig",
        "lat": 57.274, "lng": -5.518,
        "category": "water",
        "region": "Highland, Scotland",
        "summary": "A Highland spirit who appears as a beautiful grey-clad woman concealing the lower body of a goat beneath her long skirts. She could be protective — herding cattle and caring for children — or predatory, luring men to dance with her until she drained their blood. Milk offerings kept her benevolent.",
        "source": "https://en.wikipedia.org/wiki/Glaistig"
    },
    {
        "name": "Bean Nighe",
        "lat": 57.442, "lng": -5.071,
        "category": "ghost",
        "region": "Highland, Scotland",
        "summary": "The washerwoman at the ford — a small, webbed-footed spirit found scrubbing blood-stained shrouds in running water. To see her is to know that death is coming. If you can sneak behind her and take her breast, she must grant you a wish before she will let you go.",
        "source": "https://en.wikipedia.org/wiki/Bean_Nighe"
    },
    {
        "name": "Boggarts",
        "lat": 53.794, "lng": -1.751,
        "category": "fairy",
        "region": "Yorkshire & Lancashire",
        "summary": "Malevolent household and landscape spirits afflicting the north of England, curdling milk, tangling hair, and tormenting livestock. Unlike the helpful brownie, a boggart cannot be appeased — only avoided. Some are tied to specific lanes, bridges, or boggy hollows, making certain crossroads dangerous at night.",
        "source": "https://en.wikipedia.org/wiki/Boggart"
    },
    {
        "name": "Pixie",
        "lat": 50.537, "lng": -4.479,
        "category": "fairy",
        "region": "Cornwall & Devon",
        "summary": "Small, mischievous fae of the West Country with pointed ears and a gift for leading travellers astray — being pixie-led means going in circles until you turn your coat inside out to break the spell. They also steal horses to ride through the night, returning them exhausted and sweated by dawn.",
        "source": "https://en.wikipedia.org/wiki/Pixie"
    },
    {
        "name": "Wights",
        "lat": 54.978, "lng": -2.045,
        "category": "ghost",
        "region": "Northern England",
        "summary": "Spirits that inhabit places, objects, and the land itself in Norse and Anglo-Saxon tradition. Some are protective, some malevolent. The land-wights of Britain were the spiritual guardians of the island that Norse settlers had to negotiate with before they could truly belong here.",
        "source": "https://en.wikipedia.org/wiki/Wight_(mythology)"
    },
    {
        "name": "Unicorn",
        "lat": 55.953, "lng": -3.188,
        "category": "beast",
        "region": "Scotland",
        "summary": "The national animal of Scotland — a symbol not of innocence but of proud untameability. In Scottish heraldry, the unicorn is always shown chained, because an unchained unicorn is too dangerous and too free to be trusted near a king. It was said only a virgin could tame one, and even then only briefly.",
        "source": "https://en.wikipedia.org/wiki/Unicorn#Heraldry"
    },
    {
        "name": "Griffin",
        "lat": 51.507, "lng": -0.127,
        "category": "beast",
        "region": "Britain (heraldic)",
        "summary": "A lion-bodied, eagle-headed guardian of treasure, enemy of horses, and one of the great beasts of British heraldry. Its talons were said to detect poison by changing colour. Medieval bestiaries treated it as real; its image appears on coats of arms, city crests, and pub signs across the country.",
        "source": "https://en.wikipedia.org/wiki/Griffin"
    },
    {
        "name": "Blodeuwedd",
        "lat": 52.920, "lng": -3.946,
        "category": "deity",
        "region": "Gwynedd, Wales",
        "summary": "Created from nine flowers — broom, meadowsweet and oak among them — as a wife for the hero Lleu, who could not marry a mortal. She betrayed him with a lover and conspired to kill him. As punishment the wizard Gwydion turned her into an owl, and since that day all other birds mob the owl wherever they find it.",
        "source": "https://en.wikipedia.org/wiki/Blodeuwedd"
    },
    {
        "name": "Gwyn ap Nudd",
        "lat": 51.144, "lng": -2.699,
        "category": "deity",
        "region": "Somerset / Wales",
        "summary": "King of the Tylwyth Teg and ruler of Annwn — his glass castle lies within Glastonbury Tor, where Saint Collen drove him out with holy water. He leads the Cwn Annwn on the Wild Hunt and fights an eternal battle for a woman\'s hand every May Day until the world\'s end.",
        "source": "https://en.wikipedia.org/wiki/Gwyn_ap_Nudd"
    },
    {
        "name": "Merlin",
        "lat": 51.882, "lng": -4.516,
        "category": "deity",
        "region": "Wales & Britain",
        "summary": "The greatest wizard of Britain — half-demon by birth, prophet by gift, architect of the Arthurian age. He transported Stonehenge from Ireland, foretold the coming of Arthur, and in the end was imprisoned by the enchantress Nimue in a tree, a cave, or a tower of air, depending on who tells the tale.",
        "source": "https://en.wikipedia.org/wiki/Merlin"
    },
    {
        "name": "Gawain",
        "lat": 55.865, "lng": -4.257,
        "category": "deity",
        "region": "Scotland / Arthurian Britain",
        "summary": "The most courteous of Arthur\'s knights, whose strange bargain with the Green Knight tested not his sword arm but his honour — and found it, after a moment\'s weakness, intact. His strength waxed with the morning sun and waned at noon, a hint of something older than chivalry in his blood.",
        "source": "https://en.wikipedia.org/wiki/Gawain"
    },
    {
        "name": "Lancelot",
        "lat": 51.179, "lng": -1.826,
        "category": "deity",
        "region": "Arthurian Britain",
        "summary": "The greatest knight of the Round Table and its undoing — his love for Guinevere split Arthur\'s fellowship and opened the road to Camlann. Raised beneath the waters of the Lady of the Lake, he bears a name that echoes with the supernatural. In the end he became a hermit, not far from the Table\'s ruins.",
        "source": "https://en.wikipedia.org/wiki/Lancelot"
    },
    {
        "name": "Corineus",
        "lat": 50.375, "lng": -4.142,
        "category": "giant",
        "region": "Cornwall",
        "summary": "The Trojan hero granted Cornwall as his kingdom after helping Brutus defeat the giants of Albion. He delighted in wrestling giants — his greatest feat was hurling Gogmagog from a Cornish cliff into the sea below. The cliff has been known ever since as Gogmagog\'s Leap.",
        "source": "https://en.wikipedia.org/wiki/Corineus"
    },
    {
        "name": "Gog and Magog",
        "lat": 51.515, "lng": -0.092,
        "category": "giant",
        "region": "London",
        "summary": "The last of the giants of Albion, their effigies carried in the Lord Mayor\'s Show since at least the reign of Henry V. The wooden statues in the Guildhall are their third incarnation — their predecessors were burned in the Great Fire. They are the ancient guardians of the City of London.",
        "source": "https://en.wikipedia.org/wiki/Gog_and_Magog_(England)"
    },
    {
        "name": "Camelot",
        "lat": 51.060, "lng": -2.695,
        "category": "location",
        "region": "Somerset",
        "summary": "The legendary seat of Arthur\'s kingdom — most often identified with South Cadbury hillfort in Somerset, where excavations revealed a great Dark Age feasting hall rebuilt exactly when Arthur is said to have lived. Local tradition calls the hill Camelot still, and a lane at its foot is named Arthur\'s Lane.",
        "source": "https://en.wikipedia.org/wiki/Camelot"
    },
    {
        "name": "Avalon",
        "lat": 51.144, "lng": -2.699,
        "category": "location",
        "region": "Somerset",
        "summary": "The isle of eternal rest where Arthur was carried after his final battle — identified with Glastonbury by monks who claimed to have found his grave. Arthur sleeps here still, waiting to return when Britain needs him most. Many believe the monks lied about the grave. Few doubt the legend.",
        "source": "https://en.wikipedia.org/wiki/Avalon"
    },
    {
        "name": "Plynlimon",
        "lat": 52.467, "lng": -3.782,
        "category": "giant",
        "region": "Ceredigion, Wales",
        "summary": "A great giant of Welsh legend whose three daughters — Hafren, Gwy, and Rheidol — raced each other from his summit to the sea. Hafren reached the sea first, winning greatest fame, and her name became the River Severn. Plynlimon watches still from the highest ground in mid-Wales, father of rivers.",
        "source": "https://en.wikipedia.org/wiki/Plynlimon"
    },
    {
        "name": "Hafren",
        "lat": 51.856, "lng": -2.241,
        "category": "deity",
        "region": "Welsh Marches",
        "summary": "Britain\'s longest river, named for Sabrina — a princess drowned in its waters by a wicked stepmother and transformed into a river goddess. Milton gave her immortal verse in Comus. The river was once considered sacred, its banks the boundary between Britain and the Otherworld.",
        "source": "https://en.wikipedia.org/wiki/Sabrina_(goddess)"
    },
    {
        "name": "Gwy",
        "lat": 51.617, "lng": -2.660,
        "category": "deity",
        "region": "Welsh Marches",
        "summary": "The second daughter of the giant Plynlimon, who raced her sisters from the mountain summit to the sea. She became the River Wye — a liminal boundary between Wales and England, civilisation and wilderness. Her valley holds Tintern Abbey and some of the oldest oak forest in Britain.",
        "source": "https://en.wikipedia.org/wiki/River_Wye"
    },
    {
        "name": "Rheidol",
        "lat": 52.415, "lng": -3.982,
        "category": "deity",
        "region": "Ceredigion, Wales",
        "summary": "The third daughter of the giant Plynlimon, who raced her sisters Hafren and Gwy to the sea. She became the River Rheidol — shorter and wilder than her sisters, tumbling through gorges to Aberystwyth. Of the three, she is the least known but perhaps the most spirited.",
        "source": "https://en.wikipedia.org/wiki/River_Rheidol"
    },
    {
        "name": "Elder Mother",
        "lat": 52.640, "lng": -0.993,
        "category": "deity",
        "region": "East Midlands",
        "summary": "The spirit who lives within the elder tree — she must be asked permission before any branch is cut. To burn elder wood without asking brings death to the household within the year. In Scandinavia she is Hyldemor; in England she has no name, only the quiet authority of very old wood.",
        "source": "https://en.wikipedia.org/wiki/Elder_(tree)#Folklore"
    },
    {
        "name": "Gooseberry Wife",
        "lat": 50.690, "lng": -1.292,
        "category": "fairy",
        "region": "Isle of Wight",
        "summary": "A great caterpillar-like spirit said to guard gooseberry bushes on the Isle of Wight, keeping children from stealing fruit before it was ripe. Her name alone was enough to keep small hands away from the patch — whether she was real or merely a parents\' invention, the gooseberries remained unmolested.",
        "source": "https://en.wikipedia.org/wiki/Gooseberry_Wife"
    },
    {
        "name": "Brown Man of the Muirs",
        "lat": 55.274, "lng": -2.165,
        "category": "fairy",
        "region": "Northumberland",
        "summary": "A small, fierce guardian spirit of the Border moors, protector of moorland animals from hunters who killed more than they needed. He appeared in terrible form to warn the greedy. Those who ignored him met with accidents, madness, or worse before they reached home.",
        "source": "https://en.wikipedia.org/wiki/Brown_Man_of_the_Muirs"
    },
    {
        "name": "Salmon of Knowledge",
        "lat": 53.710, "lng": -6.352,
        "category": "water",
        "region": "Ireland",
        "summary": "The greatest fish in the world, which fed on nine hazelnuts of wisdom fallen into the Well of Segais. Whoever tasted it first would gain all knowledge. The druid Finnegas caught it after seven years of searching — but his servant Fionn, burning his thumb on it as he cooked, licked the blister and gained the gift instead.",
        "source": "https://en.wikipedia.org/wiki/Salmon_of_Knowledge"
    },
    {
        "name": "Helen Duncan",
        "lat": 56.130, "lng": -3.936,
        "category": "witch",
        "region": "Fife, Scotland",
        "summary": "The last person imprisoned under Britain\'s Witchcraft Act of 1735. A medium who claimed to materialise spirits of the dead, she was arrested in 1944 after apparently revealing that HMS Barham had sunk — a fact the Admiralty had not yet made public. Convicted and imprisoned, she died in 1956 shortly after a police raid on one of her séances.",
        "source": "https://en.wikipedia.org/wiki/Helen_Duncan"
    },
    {
        "name": "Mother Ludlam",
        "lat": 51.182, "lng": -0.733,
        "category": "witch",
        "region": "Surrey",
        "summary": "A benevolent witch who lived in a cave near Frensham in Surrey, lending household items to those who needed them from her magic cauldron. When a borrower failed to return it within three days, she refused to lend anything more. The cauldron still sits in Frensham church as proof of the broken bargain.",
        "source": "https://en.wikipedia.org/wiki/Mother_Ludlam"
    },
    {
        "name": "Dick Turpin",
        "lat": 53.959, "lng": -1.087,
        "category": "ghost",
        "region": "Yorkshire",
        "summary": "The highwayman hanged at York in 1739 whose ghost — or the ghost of his horse Black Bess — is said to ride the old coach roads of Yorkshire still. The real Turpin was a brutal criminal; legend transformed him into a dashing folk hero, one of the great reinventions in British popular mythology.",
        "source": "https://en.wikipedia.org/wiki/Dick_Turpin"
    },
    {
        "name": "Blue Men of the Minch",
        "lat": 57.902, "lng": -6.346,
        "category": "water",
        "region": "Outer Hebrides",
        "summary": "Storm kelpies who swim the strait between Lewis and the Shiant Isles, their grey faces rising from the foam. They challenge passing captains to a battle of rhyming verse — fail and they drag the vessel under. In calm weather they sleep beneath the surface; their restlessness is what makes the Minch so treacherous.",
        "source": "https://en.wikipedia.org/wiki/Blue_men_of_the_Minch"
    },

    # ── IRISH MYTHOLOGY & FOLKLORE ─────────────────────────────────────────
    {
        "name": "The Dagda",
        "lat": 53.694, "lng": -6.776,
        "category": "deity",
        "region": "County Meath, Ireland",
        "summary": "The Good God of Irish mythology — father-figure of the Tuatha Dé Danann, keeper of the inexhaustible cauldron from which none went hungry, wielder of a club so vast it took eight men to carry. One end killed the living; the other raised the dead. He feasted and loved without shame and ruled with tremendous power.",
        "source": "https://en.wikipedia.org/wiki/Dagda"
    },
    {
        "name": "Cú Chulainn",
        "lat": 54.351, "lng": -8.288,
        "category": "deity",
        "region": "County Sligo, Ireland",
        "summary": "The Hound of Ulster — Ireland's greatest hero, son of the sun god Lugh, who single-handedly defended Ulster against the armies of Connacht while his warriors lay cursed. He entered his battle-fury called the ríastrad, a contortion so terrible his own allies fled from him.",
        "source": "https://en.wikipedia.org/wiki/Cú_Chulainn"
    },
    {
        "name": "Fionn mac Cumhaill",
        "lat": 54.994, "lng": -7.309,
        "category": "deity",
        "region": "County Antrim, Ireland",
        "summary": "Leader of the Fianna and Ireland's great warrior-hero, who gained all wisdom by burning his thumb on the Salmon of Knowledge and touching it to his lips. He built the Giant's Causeway to fight his Scottish rival. He sleeps in a cave with his warriors, ready to wake when Ireland truly needs him.",
        "source": "https://en.wikipedia.org/wiki/Fionn_mac_Cumhaill"
    },
    {
        "name": "Tuatha Dé Danann",
        "lat": 53.694, "lng": -6.776,
        "category": "deity",
        "region": "Ireland",
        "summary": "The divine race who ruled Ireland before the Gaels arrived — gods of skill, craft, beauty and war. Defeated at the Battle of Tailteann, they retreated into the hollow hills and became the Aos Sí. Their four treasures — the Spear of Lugh, the Sword of Light, the Cauldron of Plenty, and the Stone of Destiny — are the foundation of Irish sovereignty.",
        "source": "https://en.wikipedia.org/wiki/Tuatha_Dé_Danann"
    },
    {
        "name": "Banshee",
        "lat": 53.349, "lng": -6.260,
        "category": "ghost",
        "region": "Ireland",
        "summary": "The bean sídhe — the woman of the fairy mound — whose keening wail in the night foretells the death of someone from one of the great Irish families. She may appear as a young woman combing her hair, a matron, or a hideous hag. To hear her is not to cause death, only to be warned of it.",
        "source": "https://en.wikipedia.org/wiki/Banshee"
    },
    {
        "name": "Pooka",
        "lat": 53.144, "lng": -7.692,
        "category": "fairy",
        "region": "Ireland",
        "summary": "A shape-shifting spirit of Irish folklore — most often a dark horse with burning eyes that offers rides to unwary travellers before galloping at terrifying speed through bogs and rivers until dawn, when it vanishes and leaves its rider far from home and shaking. It can also take the form of a goat, rabbit, or goblin.",
        "source": "https://en.wikipedia.org/wiki/Púca"
    },
    {
        "name": "Children of Lir",
        "lat": 54.270, "lng": -9.050,
        "category": "deity",
        "region": "County Mayo, Ireland",
        "summary": "Four children transformed into swans by their jealous stepmother for nine hundred years — three hundred on the waters of Lough Derravaragh, three hundred on the Sea of Moyle between Ireland and Scotland, three hundred on the waters of Erris. Their singing was so beautiful that all who heard it forgot their sorrows.",
        "source": "https://en.wikipedia.org/wiki/Children_of_Lir"
    },
    {
        "name": "Balor of the Evil Eye",
        "lat": 55.229, "lng": -8.329,
        "category": "giant",
        "region": "County Donegal, Ireland",
        "summary": "The terrible king of the Fomorians, whose single great eye — kept shut by a ring — would kill all it looked upon when opened. It took four men to lift his eyelid in battle. His own grandson Lugh slew him with a slingshot through the eye, fulfilling a prophecy Balor had tried all his life to prevent.",
        "source": "https://en.wikipedia.org/wiki/Balor"
    },
    {
        "name": "The Selkie (Irish tradition)",
        "lat": 54.992, "lng": -8.706,
        "category": "water",
        "region": "County Donegal, Ireland",
        "summary": "The rón — seal-folk of Irish and Scottish tradition who shed their skins to walk as humans on land. Along the Donegal coast, many families claim selkie ancestry. A fisherman who hides a selkie woman's skin keeps her on land as his wife, but if she ever finds it hidden, she will return to the sea without a backward glance.",
        "source": "https://en.wikipedia.org/wiki/Selkie"
    },
    {
        "name": "Hill of Tara",
        "lat": 53.579, "lng": -6.611,
        "category": "location",
        "region": "County Meath, Ireland",
        "summary": "The ancient seat of the High Kings of Ireland, where sovereignty itself was tested by the Lia Fáil — the Stone of Destiny that cried out beneath the rightful king. The Banquet Hall could seat the whole of Ireland. Below it the Tuatha Dé Danann built their great mound. It is the spiritual centre of Ireland.",
        "source": "https://en.wikipedia.org/wiki/Hill_of_Tara"
    },
    {
        "name": "Newgrange",
        "lat": 53.695, "lng": -6.476,
        "category": "location",
        "region": "County Meath, Ireland",
        "summary": "A passage tomb older than Stonehenge, built to align with the rising sun on the winter solstice — when light floods the inner chamber for seventeen minutes at dawn. In Irish mythology it is the home of Aengus, god of love and youth, who tricked his father the Dagda out of it by asking to stay for a day and a night — and claiming all days and nights are made of those.",
        "source": "https://en.wikipedia.org/wiki/Newgrange"
    },
    {
        "name": "Croagh Patrick",
        "lat": 53.761, "lng": -9.659,
        "category": "location",
        "region": "County Mayo, Ireland",
        "summary": "Ireland's holy mountain, where Saint Patrick fasted for forty days and drove the serpents from Ireland. Before Patrick, it was the sacred mountain of the god Lugh, and his festival Lughnasadh was celebrated on its summit. Pilgrims still climb it barefoot on the last Sunday of July, as they have for three thousand years.",
        "source": "https://en.wikipedia.org/wiki/Croagh_Patrick"
    },
    {
        "name": "The Giant's Causeway",
        "lat": 55.240, "lng": -6.511,
        "category": "giant",
        "region": "County Antrim, Ireland",
        "summary": "Forty thousand interlocking basalt columns on the Antrim coast, built by the giant Fionn mac Cumhaill as a road to Scotland so he could fight his rival Benandonner. When Fionn saw his opponent's size, his wife disguised him as a baby — and Benandonner, terrified by the size of the 'infant', fled back to Scotland, tearing up the road behind him.",
        "source": "https://en.wikipedia.org/wiki/Giant%27s_Causeway"
    },
    {
        "name": "Cailleach Bhéara",
        "lat": 51.638, "lng": -9.853,
        "category": "deity",
        "region": "County Cork, Ireland",
        "summary": "The ancient hag of the Beara Peninsula — one of the oldest figures in Irish and Scottish mythology. She has lived through seven human lifetimes, each renewed by marrying a young husband who aged and died. She shaped the mountains, drove her cattle across the sky as clouds, and now sits as stone at the tip of the peninsula, waiting.",
        "source": "https://en.wikipedia.org/wiki/Cailleach"
    },
    {
        "name": "Knocknarea",
        "lat": 54.270, "lng": -8.553,
        "category": "location",
        "region": "County Sligo, Ireland",
        "summary": "A great limestone hill above Sligo Bay, crowned with a vast cairn said to be the tomb of Queen Medb of Connacht. She is buried standing upright, facing Ulster, her eternal enemy. By tradition, every visitor adds a stone to the cairn — to take one away brings misfortune. Medb may still be inside, armed and waiting.",
        "source": "https://en.wikipedia.org/wiki/Knocknarea"
    },
    {
        "name": "Queen Medb",
        "lat": 54.270, "lng": -8.553,
        "category": "deity",
        "region": "County Sligo, Ireland",
        "summary": "Queen of Connacht and one of the most formidable figures in Irish mythology — she launched the great Cattle Raid of Cooley to steal the Brown Bull of Ulster from Cú Chulainn's people. Sovereign goddess as much as warrior queen, no king could rule Connacht without first mating with her. She was finally slain by a piece of cheese.",
        "source": "https://en.wikipedia.org/wiki/Medb"
    },
    {
        "name": "Lough Derg (St Patrick's Purgatory)",
        "lat": 54.609, "lng": -7.863,
        "category": "location",
        "region": "County Donegal, Ireland",
        "summary": "An island in Lough Derg said to contain a cave leading directly to Purgatory — revealed to Saint Patrick so he could show doubters what awaited sinners. Medieval pilgrims came from across Europe to descend into it. The penitential tradition continues to this day: three days without sleep, barefoot on the cold stone island.",
        "source": "https://en.wikipedia.org/wiki/Lough_Derg_(Ulster)"
    },
    # Curated pirates: pin British Isles birthplace unless a stronger local
    # association exists, as with Grace O'Malley's base at Rockfleet Castle.
    {
        "name": "Bartholomew Roberts",
        "lat": 51.9223, "lng": -4.9388,
        "category": "pirate",
        "region": "Little Newcastle, Pembrokeshire",
        "summary": "The Welsh pirate Barti Ddu, later called Black Bart, captured more than four hundred vessels during the Golden Age of Piracy. His birthplace at Little Newcastle still bears a memorial stone.",
        "source": "https://en.wikipedia.org/wiki/Bartholomew_Roberts"
    },
    {
        "name": "Grace O'Malley",
        "lat": 53.8960, "lng": -9.6271,
        "category": "pirate",
        "region": "Rockfleet Castle, County Mayo",
        "summary": "The sea-captain Gráinne Ní Mháille ruled the shores of Clew Bay and negotiated with Elizabeth I as an equal. Rockfleet Castle, her stronghold on the tidewater, remains the place most closely bound to her legend.",
        "source": "https://en.wikipedia.org/wiki/Grace_O%27Malley"
    },
    {
        "name": "Henry Every",
        "lat": 50.3167, "lng": -4.0333,
        "category": "pirate",
        "region": "Newton Ferrers, Devon",
        "summary": "Born near Plymouth, the elusive Henry Every became the Arch Pirate after taking an immense Mughal treasure ship in 1695. A worldwide hunt followed, but he vanished without a proven end.",
        "source": "https://en.wikipedia.org/wiki/Henry_Every"
    },
    {
        "name": "Howell Davis",
        "lat": 51.7140, "lng": -5.0420,
        "category": "pirate",
        "region": "Milford Haven, Pembrokeshire",
        "summary": "The Milford Haven pirate Howell Davis relied on disguise and deception as readily as cannon fire. His short career lasted less than a year, yet he captured fifteen known ships before an ambush ended it.",
        "source": "https://en.wikipedia.org/wiki/Howell_Davis"
    },
    {
        "name": "William Kidd",
        "lat": 56.4620, "lng": -2.9707,
        "category": "pirate",
        "region": "Dundee, Scotland",
        "summary": "The Dundee-born privateer Captain Kidd was sent to hunt pirates and returned accused of piracy himself. His execution and rumours of buried treasure transformed a disputed career into enduring legend.",
        "source": "https://en.wikipedia.org/wiki/William_Kidd"
    },
]


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
                    if lat and lng:
                        coords[title] = (float(lat), float(lng))
            time.sleep(RATE_LIMIT)
        except Exception as e:
            if verbose:
                print(f"      [!] GeoData batch failed: {e}")
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
    """Rough bounding box check — filters out entries placed outside Britain."""
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
    "Redcap": "ghost", "The Black Dog of Newgate": "ghost",
    "Cock Lane ghost": "ghost", "Bean Nighe": "ghost",
    "Lantern Man": "ghost", "Banshee": "ghost", "Wights": "ghost",
    "Nanny Rutt": "water", "Glaistig": "water",
    "Blue Men of the Minch": "water", "Salmon of Knowledge": "water",
    "Maeshowe Runes": "location", "Orkneyinga Saga": "location",
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
    "Trow": "fairy", "Pooka": "fairy", "Aos Sí": "fairy",
    "Tylwyth Teg": "fairy", "Seelie Court": "fairy",
    "Unseelie Court": "fairy", "Boggarts": "fairy",
    "Pixie": "fairy", "Yallery Brown": "fairy",
    "Brown Man of the Muirs": "fairy", "Gooseberry Wife": "fairy",
    "Hyter Sprite": "fairy",
    "Filey Dragon": "dragon", "Gurt Worm": "dragon",
    "Mordiford Dragon": "dragon",
    "Black Annis": "beast", "Wisht Hounds": "beast",
    "Renwick Cockatrice": "beast", "Fad Felen": "beast",
    "Grace O\'Malley": "pirate", "Blackbeard": "pirate",
    "Anne Bonny": "pirate", "Mary Read": "pirate",
    "Black Bart Roberts": "pirate", "Calico Jack": "pirate",
    "Henry Every": "pirate", "William Kidd": "pirate",
    "Davy Jones": "pirate",
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


def apply_cleanup(legends: dict) -> dict:
    removed = fixed = 0
    for name in list(legends.keys()):
        if name in REMOVE_ENTRIES:
            del legends[name]
            removed += 1
    for leg in legends.values():
        original = leg["category"]
        if leg["name"] in FORCE_CATEGORY:
            leg["category"] = FORCE_CATEGORY[leg["name"]]
        if leg["category"] in CATEGORY_REMAP:
            leg["category"] = CATEGORY_REMAP[leg["category"]]
        if leg["category"] not in VALID_CATEGORIES:
            leg["category"] = "beast"
        if leg["category"] != original:
            fixed += 1
    print(f"      Cleanup: removed {removed}, fixed {fixed} categories")
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
        "https://inspire.hes.scot/arcgis/rest/services/INSPIRE/Scottish_Cultural_ProtectedSites/MapServer/0/query",
        "location"
    ),
    "Protected Wrecks": (
        "https://inspire.hes.scot/arcgis/rest/services/INSPIRE/Scottish_Cultural_ProtectedSites/MapServer/4/query",
        "pirate"
    ),
    "Gardens and Landscapes": (
        "https://inspire.hes.scot/arcgis/rest/services/INSPIRE/Scottish_Cultural_ProtectedSites/MapServer/5/query",
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


def _he_term_relevant(name: str, desc: str = "") -> bool:
    """Return True if the site name or description suggests folkloric relevance."""
    text = (name + " " + desc).lower()
    return any(t in text for t in HES_FOLKLORE_TERMS)

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
                features = data.get("features", [])

                if not features:
                    break

                for feat in features:
                    props   = feat.get("properties", {})
                    site_id = (props.get("SM_UID") or props.get("LB_UID") or
                               props.get("SM_REF") or props.get("OBJECTID") or
                               props.get("FID"))
                    if not site_id or str(site_id) in seen_ids:
                        continue
                    seen_ids.add(str(site_id))

                    # Get centroid — ArcGIS polygons need manual centroid calc
                    geom = feat.get("geometry", {})
                    lat = lng = None

                    if geom:
                        # Point geometry
                        if geom.get("x") is not None:
                            lng, lat = float(geom["x"]), float(geom["y"])
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

                    if not lat or not lng:
                        continue
                    if not is_in_uk(float(lat), float(lng)):
                        continue

                    name = (props.get("SM_NAME") or props.get("LB_NAME") or
                            props.get("SITE_NAME") or props.get("NAME") or "").strip()
                    if not name:
                        continue

                    desc = (props.get("SM_DESCR") or props.get("DESCRIPTION") or
                            props.get("DESC_") or "").strip()

                    # Ordinary protected wrecks are not pirate lore.
                    if category == "pirate" and not _pirate_term_relevant(name, desc):
                        continue
                    if category != "pirate" and not _he_term_relevant(name, desc):
                        continue

                    # Build summary
                    period = (props.get("PERIOD") or props.get("SM_PERIOD") or "").strip()
                    if desc:
                        summary = desc[:450]
                        if len(desc) > 450:
                            cut = summary.rfind(". ")
                            summary = summary[:cut + 1] if cut > 150 else summary[:447] + "..."
                    else:
                        parts   = [p for p in [period] if p]
                        summary = f"{name} — {', '.join(parts)}." if parts else                                   f"{name} — a protected heritage site in Scotland."

                    sm_ref = props.get("SM_REF") or props.get("LB_REF") or site_id
                    source = f"https://www.trove.scot/record/{sm_ref}"
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
            except requests.exceptions.RequestException as e:
                print(f"    [HES] Error on {layer_name}: {e}")
                break

        if verbose:
            print(f"    [HES] {layer_name}: done")
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
    n = name.lower()
    return any(t in n for t in NHLE_FOLKLORE_TERMS)

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
                "outFields":          "NAME,ENTRY_NAME,ENTRY_NUMBER,GRADE,PERIOD,DESCRIPTION,OBJECTID",
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
                features = data.get("features", [])

                if not features:
                    break

                for feat in features:
                    attrs   = feat.get("attributes", {})
                    site_id = (attrs.get("ENTRY_NUMBER") or
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

                    if not lat or not lng:
                        continue
                    if not is_in_uk(float(lat), float(lng)):
                        continue

                    name = (attrs.get("NAME") or
                            attrs.get("ENTRY_NAME") or "").strip()
                    if not name:
                        continue

                    desc   = (attrs.get("DESCRIPTION") or "").strip()
                    period = (attrs.get("PERIOD") or "").strip()
                    grade  = (attrs.get("GRADE") or "").strip()

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

                    entry_no = attrs.get("ENTRY_NUMBER", "")
                    source   = (f"https://historicengland.org.uk/listing/the-list/list-entry/{entry_no}"
                                if entry_no else "https://historicengland.org.uk")
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
            except requests.exceptions.RequestException as e:
                print(f"    [Historic England] Error on {layer_name}: {e}")
                break

        if verbose:
            print(f"    [Historic England] {layer_name}: done")
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
SUPABASE_URL         = _os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = _os.getenv("SUPABASE_SERVICE_KEY", "")


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
            "name":     r["name"],
            "lat":      r["lat"],
            "lng":      r["lng"],
            "category": r.get("category", "beast"),
            "region":   r.get("region", "Britain"),
            "summary":  r.get("summary", ""),
            "source":   r.get("source", ""),
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
          supabase_prune: bool = False) -> None:
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
            entry = {
                "name":     title,
                "lat":      round(lat, 4),
                "lng":      round(lng, 4),
                "category": all_titles.get(title, "beast"),
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
    print(f"\n  [4/4] Writing legends.json ...")
    output = {
        "generated":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total":      len(legends),
        "categories": CATEGORY_LABELS,
        "legends":    sorted(legends.values(), key=lambda x: x["name"])
    }
    with open("legends.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"      Total legends : {len(legends)}")
    print(f"      File written  : legends.json")

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
    parser.add_argument("--verbose", "-v",       action="store_true",
        help="Show each API call")
    args = parser.parse_args()
    if args.supabase_prune and not args.supabase:
        parser.error("--supabase-prune requires --supabase")
    build(
        limit=args.limit,
        seed_only=args.seed_only,
        verbose=args.verbose,
        use_hes=args.hes,
        use_he=args.historic_england,
        use_dbpedia=args.dbpedia,
        supabase=args.supabase,
        supabase_prune=args.supabase_prune,
    )


if __name__ == "__main__":
    main()
