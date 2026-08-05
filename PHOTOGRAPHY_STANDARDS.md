# Photography & Illustration Standards

Internal reference doc — not published to the site. Covers the visual standard for legend
hero images (currently 100% AI-generated) and the baseline that would apply if real
photography is ever added. Pairs with the AI-image-disclosure policy in [BRAND_GUIDE.md](BRAND_GUIDE.md)
and [editorial.html](editorial.html), which this doc doesn't repeat.

## Core visual system (as established across ~665 hero images)

Every published hero image already follows the same unwritten style. This section writes
down what's actually there, from inspecting the existing set, so new images stay consistent
rather than each one being a fresh art-direction decision.

- **Cinematic photoreal, not painterly or illustrative.** Rendered like a still from a nature
  or historical documentary — sharp, physically plausible detail (weather, stone texture,
  water, weathered wood), not a flat digital-painting or fantasy-book-cover look.
- **Low, moody light.** Overcast, dusk, dawn, storm-light or deep blue "magic hour" —
  overwhelmingly preferred over flat bright daylight. Skies do a lot of the emotional work.
- **Muted, desaturated, cool-leaning palette.** Slate blues, stone greys, bracken browns,
  moss greens. Colour is used sparingly as an accent (a lit window, a lantern, a creature's
  eyes), not as the dominant note.
- **Landscape-first composition.** The subject (creature, figure, or site) is placed *within*
  a real-feeling British/Irish landscape or building, usually not dead-centre — a wide
  establishing shot with the subject integrated, not a portrait/hero-shot crop.
- **Authentic, period-plausible setting.** Real-feeling vernacular architecture (flint or
  granite church towers, drystone walls, moorland, coastline), no anachronistic elements,
  no generic fantasy-world dressing.
- **Human figures kept distant, obscured, or turned away.** When people appear, they're
  small in frame, cloaked/hooded, silhouetted, or facing away — never a clear, camera-aware
  face. This is a deliberate constraint, not an accident: it avoids the image reading as a
  claimed likeness of a real historical person, and keeps focus on the landscape and the
  creature/event rather than a posed character.
- **No on-image text, logos, watermarks, or UI elements** of any kind.

## Technical specification

- **Aspect ratio / size:** 16:9, master delivered at 1600×900 (a handful of legacy entries are
  ~1670×940 — near enough, don't chase pixel-perfect uniformity on old assets, but new
  generations should target 1600×900 exactly).
- **Format:** JPEG, quality ~82, optimized + progressive. `generate_pages.py`
  (`build_webp_heroes`, `build_card_thumbs`) automatically derives a WebP sibling and an
  800px-wide card thumbnail from every `*-hero.jpg` on each build — never hand-create these,
  just drop the JPEG in and rebuild.
- **File naming:** `{legend-slug}-hero.jpg`, placed in `legend-images/`. The slug must match
  the one `generate_pages.py` derives from the legend name (`slugify()`), so it resolves
  automatically.
- **Metadata to fill in per image**, in `legend_pages.json` under the legend's entry:
  - `image` — the path above.
  - `alt` — a plain, concrete scene description (what's literally visible), not the legend's
    name or a sales pitch. E.g. *"A huge black dog crossing a rain-soaked lane near a
    medieval Norfolk church"*, not *"Black Shuck illustration"*.
  - `caption` — short, e.g. *"A visual interpretation of the East Anglian legend"*. Keep this
    generic across entries rather than reinventing the phrasing each time.

## Prompt template

Use this shape (same pattern as `_drafts/achievement-icon-style-guide.md` uses for
achievement seals) so new heroes stay stylistically cohesive with the existing set instead of
drifting per-session:

```
Use case: hero illustration for a folklore-map legend page
Asset type: 16:9 cinematic landscape photo, 1600x900
Primary request: a photorealistic scene depicting {legend / creature / event}
Subject: {creature or figure}, kept distant/silhouetted/obscured if a human figure is shown
Setting: {real place name / county}, {specific landscape or building detail — church tower,
  standing stones, coastline, moor, etc.}
Style/medium: cinematic photoreal, documentary-still quality, sharp physical detail
Lighting/mood: overcast / dusk / dawn / storm-light, low and moody, "magic hour" blues
  preferred over flat daylight
Color palette: muted, desaturated, cool-leaning (slate, stone, moss, bracken) with colour
  used only as a small accent
Composition/framing: landscape-first wide shot, subject integrated into the scene rather
  than centred as a portrait
Constraints: no on-image text, no logos, no watermark, no anachronistic objects, no clear
  camera-aware human face, period-plausible architecture and dress
```

## AI-disclosure (mandatory, already automated)

Every hero image on a legend or collection page carries the fixed-wording disclosure —
*"Illustration created with the assistance of generative AI."* — rendered automatically by
`generate_pages.py` beneath the image (`.hero-ai-note` / `.col-hero-credit`). This is not
optional per-image and the wording must not be paraphrased; see BRAND_GUIDE.md's AI-image
disclosure section for the policy rationale. Nothing in this doc changes that — a future
switch to real photography for a given entry wouldn't get this caption, so `legend_pages.json`
would need a way to mark an image as non-AI before that caption logic can be trusted (not
built yet, since every current image is AI-generated).

## If real photography is ever used

Not currently used anywhere on the site — flagging the baseline now so it doesn't get
skipped later, since the proposal names photography alongside illustration standards:

- Must be either originally shot for the site, or used under a licence that permits
  commercial reuse with attribution (e.g. CC BY / CC BY-SA, or explicit permission) — never
  scraped from an unlicensed source.
- Photographer/source credit is mandatory in the same caption slot the AI-disclosure uses
  today, e.g. *"Photograph: {name/source}, {licence}"*.
- Same technical spec as above (1600×900, JPEG→WebP pipeline) so it drops into the existing
  template without special-casing.
- Should meet the same compositional standard where practical (landscape-first, muted
  palette) so a mixed AI/photo set doesn't look inconsistent — but a genuine historical or
  site photograph is valuable specifically *because* it's real, so don't force a real photo
  to imitate the AI look at the cost of authenticity.
