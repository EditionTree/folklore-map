# Folklore Finder Brand & Voice Guide

Phase 0 of the brand roadmap (see `i-ve-created-a-proposal-swift-bee.md` plan). This is the
copy/terminology foundation that later phases (homepage, My Archive, achievements, collections,
legend pages, editorial policy, AI transparency) should be written against. Treat this as a
reference document, alongside `STYLE_GUIDE.md` (site chrome) and `content-style-guide.md`
(legend-detail prose rules).

## 1. Positioning statement

> **The folklore atlas of Britain and Ireland.**

Use this as the category definition — in meta descriptions, the About page, press material, and
anywhere the site needs to say what it *is* in one line. It draws a clear line against folklore
blogs, general mythology encyclopedias, and travel-entertainment sites: Folklore Finder is
specifically geographic and specifically an atlas.

## 2. Tagline

> **Every place has a story.**

Primary emotional promise. Use as the homepage hero subhead candidate, social bio opener, and
campaign phrase across social/print/merchandise. It is short enough to survive being cropped on
social platforms and generic enough to work for any region or legend type.

## 3. Longer emotional promise (for supporting copy, not headlines)

> Find the stories rooted in the landscape.

Use this where the tagline needs one more clause of support — e.g. directly under the hero
headline, or as a strapline on regional landing pages.

## 4. Brand description (one paragraph)

> Folklore Finder is a folklore atlas of Britain and Ireland: an interactive map connecting
> hundreds of researched legends, creatures and sacred places to the exact locations where their
> stories are rooted. Every entry is checked against folklore scholarship, heritage records or
> primary sources before it earns a place on the map. Explore by place, follow a theme through a
> curated collection, or let the map surprise you — and build a personal archive of what you
> discover along the way.

Use for: About page intro, press kit, partnership/media page, app-store-style listings.

## 5. Social profile bio (short form, ~150 characters)

> The folklore atlas of Britain and Ireland. Every place has a story — explore the legends rooted
> in the landscape around you.

## 6. The real point of difference

Repeat this framing wherever the site explains itself — About page, onboarding copy, press
material:

- Stories belong to places, not just to a list.
- Folklore can be explored geographically, not just alphabetically or by category.
- Familiar landscapes contain hidden cultural memory.
- Visitors can discover what was believed near where they live or travel.

Avoid describing the site as "a folklore archive" or "a folklore encyclopedia" in isolation —
always tie the description back to place. Prefer:

> The landscape around you is full of stories, and Folklore Finder helps you uncover them.

over:

> Here is a folklore archive.

## 7. Visual identity — hold the line

No changes recommended to the existing heritage-cartography identity (parchment, burnt orange,
antique gold, dark brown linework, wax seals, map motifs — see `STYLE_GUIDE.md` for the exact
tokens already codified there). Target aesthetic to keep in mind for any new component (carousel
cards, trust panel, policy page, share cards): **living heritage with a trace of the uncanny.**

Avoid drifting toward: fantasy-game UI, generic Celtic knotwork, Halloween-horror styling,
excessive gothic treatment, faux-medieval clutter, or dark-mode-only interfaces.

## 8. Brand voice

Four traits, in priority order:

1. **Evocative, not theatrical.** Landscape/memory/path/stone/river/coastline/boundary/weather
   language is welcome. Avoid horror-movie or high-fantasy register.
2. **Authoritative, but accessible.** Research standards should be visible without every page
   reading like a journal article.
3. **Curious, not sensationalist.** Invite exploration; don't clickbait ("You won't believe...").
4. **Human, not corporate.** The site is independently researched and maintained — write like one
   careful person, not an anonymous institution or a committee.

### Voice rules already proven on this site

`content-style-guide.md` documents hard-won rules from a 2026-07-20 incident where the Robin Hood
legend page read as AI-written. Those rules apply beyond legend `detail` text — treat them as the
house style for **any** new prose (carousel copy, trust panel, editorial policy, AI-use
statement):

- **Narrate, don't comment.** Open with what something *is* and *does*, not with meta-commentary
  about how long people have believed it or what it "represents."
- **At most one em dash per paragraph.** Prefer a colon, full stop, or short comma appositive.
- **Avoid AI tropes**: "stands as a testament to...", "not just X, but Y", "rich tapestry",
  "steeped in", "woven into the fabric of", overused triadic rhythm ("sometimes X, sometimes Y,
  always Z").
- **Vary sentence length and structure** so nothing reads like a template being filled in.

### Run every new page of copy through `no-ai-slop`

`content-style-guide.md` is Folklore Finder-specific (it was written *from* a real incident on
this site). The `no-ai-slop` skill is the general-purpose version of the same problem and is
stricter and more exhaustive — use both together, not one instead of the other:

- **Before publishing** any new prose this roadmap produces (homepage carousel cards, trust
  panel, empty states, continuation prompts, editorial policy, AI-use statement, collection
  guides, Field Notes articles), run it through the `no-ai-slop` skill's **edit** mode.
- When reviewing existing copy for the terminology audit (§12), or spot-checking a legend page,
  use its **detect** mode first — it names the specific pattern and quotes the line, which is
  more useful for an audit than a silent rewrite.
- `no-ai-slop`'s banned-words list and pattern list are broader than `content-style-guide.md`'s
  (which only calls out the tropes that actually showed up in this site's drafts). Treat
  `content-style-guide.md`'s list as the site's known repeat offenders and `no-ai-slop`'s list as
  the full net — a passage can clear the site-specific list and still trip the general one.
- The two sources agree on the load-bearing rules for this site, so there's no conflict to
  resolve, only overlap to point out:
  - Both flag **"stands as a testament to"** and **"rich tapestry" / "woven into the fabric
    of"** by name.
  - `no-ai-slop`'s **"colon reveals"** and **"faux-insight setups"** patterns are the general form
    of the "narrate, don't comment" rule above — a colon-reveal opener is exactly the
    meta-commentary move the Robin Hood incident flagged.
  - `no-ai-slop`'s **em-dash guidance** ("none in short copy, 1–2 in longer drafts if they clearly
    beat commas") is slightly stricter than the site's "at most one per paragraph" — for short
    copy (CTAs, card blurbs, empty states) default to `no-ai-slop`'s zero; for longer prose
    (editorial policy, Field Notes articles, legend `detail` text) the existing one-per-paragraph
    ceiling still applies.
  - `no-ai-slop` additionally bans "delve", "leverage", "robust", "meticulous", "paramount",
    "transformative" and similar — none of these have appeared on the site yet, but they're now
    explicitly off-limits for any new copy under this roadmap.
- `no-ai-slop`'s **workflow step 2** (identify the core point and 3–5 voice signals to preserve
  before editing) matters here specifically because Folklore Finder's voice already has real
  personality (see the Black Shuck / Arthur openings quoted in `content-style-guide.md`) — the
  goal is removing AI tells, not sanding the site down to generic polished prose.

This matters especially for the new AI-use policy and editorial policy pages (§11 below) — they
should read as plainly human-written as the legend pages already strive to.

## 9. Standardised exploration verbs

Use these consistently across CTAs, empty states, and progress copy — this is what makes the
experience feel like one connected system rather than several separate features.

| Verb | Use for |
|---|---|
| Explore the map | Primary CTA to the interactive map |
| Visit a legend | Opening/reading a single entry |
| Save a story | Bookmarking a legend to My Archive |
| Discover a region | Browsing by place |
| Begin a collection | First entry into a themed collection |
| Continue a collection | Returning to an in-progress collection |
| Complete a collection | All entries in a collection visited |
| Unlock a seal | Earning an achievement |
| Build your archive | General framing for My Archive as a destination |

Current site copy mostly already matches this vocabulary (e.g. "Explore the map" CTA in
`index.html` line 636 is correct as-is). See §12 for the specific places that don't yet match.

## 10. Origin-period dating methodology note

Covers the `origin_date` / `earliest_record` / `period` / `historical_setting` /
`cultural_tradition` / `origin_type` / `dating_confidence` / `alt_names` fields added in
`supabase/migrations/20260706130000_add_historical_metadata.sql`, ahead of the Phase 4 rollout
across all entries. Establishing the phrasing convention here now means the Phase 4 content pass
can apply it mechanically rather than re-deciding tone per entry.

**Principle:** state the confidence level plainly rather than implying more precision than the
evidence supports. Never present folk-belief dating as if it were a documented historical record.

Suggested phrasing by `dating_confidence` tier:

- **Documented** (a specific text/record exists): *"First recorded in [source], [date/century]."*
- **Approximate** (a period is reasonably inferable but no single first record): *"Believed to
  date from the [period], based on [type of evidence — e.g. regional custom, place-name
  evidence]."*
- **Oral tradition / undated**: *"Passed down through oral tradition; no firm date of origin."*

`origin_type` (e.g. folk memory, historical event, literary invention, place-name legend) should
be surfaced alongside the date phrase where it changes the reading — e.g. a literary invention
with a known publication date reads differently from a place-name legend with no fixed origin.

This note should be handed to whoever performs the Phase 4 data-entry pass so phrasing stays
consistent across all 664 entries rather than drifting per contributor.

## 11. Editorial policy & AI-use policy — source copy

Draft copy for the dedicated policy page to be built in Phase 3. Written to the voice rules in
§8 — plain, first-person-plural, no hedging padding.

### Editorial policy (draft)

> **How entries are researched**
> Every legend starts as a lead: an old folklore collection, a heritage record, or a story a
> visitor sent in. Before it earns a pin on the map, we check it against folklore scholarship,
> heritage records or primary sources. Where the evidence is thin, or a tale can't be pinned to a
> real place, we hold it back rather than guess.
>
> **How locations are verified**
> Every entry is pinned to the most specific real-world location the evidence supports: a named
> site where possible, a parish or region where a single site can't be confirmed. If a legend has
> genuinely competing locations, the entry says so rather than picking one arbitrarily.
>
> **Sourcing standard**
> We rank sources by reliability: primary accounts and heritage-body records first, then
> established folklore scholarship, then secondary and popular sources to fill gaps. Weaker
> sources get flagged for follow-up, not treated as equal to stronger ones.
>
> **Disputed claims**
> Where regional variants or scholarly disagreement exist, the entry says so rather than
> flattening the story into one version.
>
> **Corrections**
> If you spot an error (a wrong location, a misattributed source, a fact that's off), [use the
> correction link on the entry / contact form] and we'll check it and fix it.
>
> **Editorial responsibility**
> Folklore Finder is an independent digital archive, researched and maintained by its creator,
> with contributions from visitors and local communities. Final editorial responsibility for
> every published entry rests with Folklore Finder, not with any source or contributor.

### AI-use statement (draft)

> AI may help organise research notes or draft a first pass of an entry on Folklore Finder. A
> person checks every fact against real sources before anything goes live, and AI is never
> treated as a source in itself.
>
> Some illustrations here are AI-generated. Where that's the case, the page says so. Final
> responsibility for every entry, text, sourcing and images, stays with Folklore Finder.

**What changed (`no-ai-slop` pass):** Consolidated the three overlapping ways the original AI-use
draft said "AI doesn't verify things" (a binary "not as a source of truth" opener, then "nothing
is published without independent human verification", then "AI does not verify folklore on its
own... never treated as a source in itself") into one plain claim, stated directly instead of as
a contrast. Fixed the mismatch between the section intro's claim of "first-person-plural" voice
and the drafts actually being written in third person — both drafts now consistently use "we" for
Folklore Finder's own actions. Replaced the two dash-flanked asides (`locations are verified`,
`Corrections`) with a colon and parentheses respectively, per `no-ai-slop`'s stricter em-dash
guidance for this length of copy. Changed the passive "it will be checked and fixed" in
Corrections to active "we'll check it and fix it." Nothing about the actual policy content
changed — no source, claim, or commitment was added or dropped.

### AI-image disclosure caption (fixed wording, use verbatim)

> Illustration created with the assistance of generative AI.

Keep this exact wording everywhere it's used (legend hero images, social assets) so it reads as a
consistent policy rather than ad hoc phrasing per page.

## 12. Copy audit — current site vs. this guide

Spot-checked `index.html` (hero, lines 614–670) and `about.html` (intro, lines 150–176) against
the terminology above.

| Location | Current copy | Assessment |
|---|---|---|
| `index.html:619` hero-edition | "A living archive of Britain & Ireland" | Close to the brand description's "atlas" framing but uses "archive" here and "atlas" elsewhere (`hero-sub`) — pick one primary noun. Recommend **"atlas"** site-wide per positioning statement (§1), reserve "archive" specifically for My Archive. |
| `index.html:622` hero-sub | "An atlas of myths, legends, & stories" | Keep — matches positioning statement. Also duplicated verbatim in the footer (`index.html:672`) and `STYLE_GUIDE.md:76`, so any change here must be applied in both places plus generated-page chrome. |
| `index.html:623` hero-lede | "Explore the myths, monsters, sacred sites and spectral figures that haunt the landscape..." | Good place-rooted language ("rooted in the place where their story lives" already present) — no change needed, already voice-aligned. |
| `index.html:636` CTA | "Explore the map" | Matches §9 vocabulary exactly. No change. |
| `about.html:11` meta description | "...how entries are researched and verified before they join the map" | Compatible with §11 editorial-policy draft; once the dedicated policy page ships, link this description to it rather than leaving the claim unsupported by a destination page. |
| `about.html:165` about-intro | "...built from folklore scholarship, heritage records and primary accounts rather than repeated hearsay." | This is effectively already the "researched, not repeated" trust-panel line the homepage is missing (proposal §3.5). Reuse this exact sentence for the new homepage trust panel rather than drafting a new one — it's already voice-correct and tested copy. |
| `about.html:168` about-intro | "...independently checked against sources before it earns a pin. Where the evidence is thin... it's held back rather than guessed at." | This is the source for the Editorial Policy draft above (§11) — copy has effectively already been written for the About page and should be promoted/expanded into the dedicated policy page, not rewritten from scratch. |

**Overall finding:** the site's existing copy is already close to this guide's voice — the main
inconsistency is **archive vs. atlas** as the primary noun for the whole site (distinct from "My
Archive" the feature). Recommend standardising on:

- **"atlas"** — the whole site, the product category (positioning statement).
- **"archive"** — reserved for the My Archive feature and its own copy ("Build your archive").

No AI-disclosure or AI-use language exists anywhere on the site today (confirmed via search of
`about.html`, `index.html`, `robots.txt`, `README.md`, `STYLE_GUIDE.md`,
`content-style-guide.md`) — §11 above is net-new copy, not a rewrite.
