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
UK_BOUNDS = {"lat_min": 49.5, "lat_max": 61.5, "lng_min": -9.0, "lng_max": 2.5}


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
    ("Category:Lake_monsters",                    "beast"),
    ("Category:Sea_monsters",                     "beast"),
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

def build(limit: int, seed_only: bool, verbose: bool) -> None:
    print("\n  Folklore Map — legend data pipeline")
    print("  " + "─" * 44)

    # Start with seed data — these always win on duplicates
    legends = {leg["name"]: leg for leg in SEED_LEGENDS}
    print(f"\n  [1/3] Seed data loaded: {len(legends)} entries")

    if seed_only:
        print("\n  [2/3] Skipped (--seed-only)")
    else:
        print(f"\n  [2/3] Fetching from Wikipedia ({len(CATEGORIES)} categories, {len(LISTS)} lists) ...")
        all_titles   = {}   # title -> category
        added        = 0
        out_of_uk    = 0
        duplicates   = 0

        # Step 1a: collect article titles from categories
        for cat_name, cat_type in CATEGORIES:
            if verbose:
                print(f"\n    Category: {cat_name}")
            members = get_category_members(cat_name, limit, verbose)
            for m in members:
                title = m["title"]
                if title not in all_titles:
                    all_titles[title] = cat_type
            time.sleep(RATE_LIMIT)

        # Step 1b: collect article titles from list pages
        print(f"      Pulling from {len(LISTS)} list articles ...")
        for list_title, list_type in LISTS:
            if verbose:
                print(f"\n    List: {list_title}")
            members = get_list_members(list_title, verbose)
            for m in members:
                title = m["title"]
                if title not in all_titles:
                    all_titles[title] = list_type
            time.sleep(RATE_LIMIT)

        print(f"      {len(all_titles)} unique articles across all sources")

        # Step 2: fetch coordinates in batches
        print(f"      Fetching coordinates ...")
        titles_list = list(all_titles.keys())
        geodata = get_article_geodata(titles_list, verbose)
        print(f"      {len(geodata)} articles have coordinates")

        # Step 3: fetch summaries for articles with UK coordinates
        print(f"      Fetching summaries for UK articles ...")
        for title, (lat, lng) in geodata.items():
            if not is_in_uk(lat, lng):
                out_of_uk += 1
                continue

            if title in legends:
                duplicates += 1
                continue

            if verbose:
                print(f"    + {title} ({lat:.3f}, {lng:.3f})")

            summary = get_article_summary(title, verbose)
            if not summary:
                summary = f"{title} — a figure from British folklore."

            category = all_titles.get(title, "beast")
            region   = infer_region(title, summary)
            source   = f"https://en.wikipedia.org/wiki/{requests.utils.quote(title.replace(' ', '_'))}"

            legends[title] = {
                "name":     title,
                "lat":      round(lat, 4),
                "lng":      round(lng, 4),
                "category": category,
                "region":   region,
                "summary":  summary,
                "source":   source,
            }
            added += 1
            time.sleep(RATE_LIMIT)

        print(f"\n      Added      : {added}")
        print(f"      Duplicates : {duplicates}")
        print(f"      Out of UK  : {out_of_uk}")
        print(f"      No coords  : {len(all_titles) - len(geodata)}")

    # Step 3: write output
    print(f"\n  [3/3] Writing legends.json ...")
    output = {
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total":     len(legends),
        "categories": CATEGORY_LABELS,
        "legends":   sorted(legends.values(), key=lambda x: x["name"])
    }
    with open("legends.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"      Total legends : {len(legends)}")
    print(f"      File written  : legends.json")
    print(f"\n  Done.\n")
    print(f"  Tip: open legends.json and review any entries with region='Britain'")
    print(f"       — these didn't match a region keyword and may need manual correction.\n")


def main():
    parser = argparse.ArgumentParser(description="Folklore Map — one-time data pipeline")
    parser.add_argument("--seed-only", action="store_true",
        help="Skip Wikipedia, just write seed data to legends.json")
    parser.add_argument("--limit", type=int, default=500,
        help="Max articles per Wikipedia category (default: 500)")
    parser.add_argument("--verbose", "-v", action="store_true",
        help="Show each API call")
    args = parser.parse_args()
    build(args.limit, args.seed_only, args.verbose)


if __name__ == "__main__":
    main()
