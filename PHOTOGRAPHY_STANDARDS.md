# Legend Image Style Guide

Internal production reference for Folklore Map legend hero images. Use this before every
generation batch. It records the visual language established by the existing image library
and the later art-direction decisions made during the category rollout.

The AI-image disclosure policy lives in [BRAND_GUIDE.md](BRAND_GUIDE.md) and
[editorial.html](editorial.html). This guide covers image selection, generation, and quality.

## Core visual identity

- **Cinematic photorealism.** Images should resemble a still from a historical, landscape,
  or natural-history documentary. Use sharp physical detail, believable weather, and tactile
  stone, water, wool, wood, skin, fur, feathers, or scales. Avoid painterly fantasy-cover art.
- **The legend is the subject.** Show the named creature, person, apparition, event, or sacred
  feature. A generic landscape, ritual object, empty building, or symbolic prop is not enough.
- **Place anchors the story.** Use recognisable British and Irish terrain, geology,
  vernacular architecture, coast, vegetation, and weather. Do not substitute generic fantasy
  scenery for the stated region.
- **Historically plausible worlds.** Match dress, tools, buildings, vessels, roads, and social
  setting to the legend's period where one is known. Avoid anachronisms and stock medievalism.
- **Moody natural light.** Overcast, dawn, dusk, storm light, moonlight, sea glare, mist, or
  firelight are preferred. Bright daylight is acceptable when the narrative calls for it, but
  flat studio-like illumination is not.
- **Restrained colour.** The usual base is slate, stone, peat, moss, bracken, sea green, and
  weathered timber. Add one controlled accent such as fire, tartan, a garment, eyes, flowers,
  or reflected light. Do not make every image uniformly dark or blue.
- **No text, logos, borders, watermarks, or UI.** No modern objects unless the legend itself
  is modern and requires them.

## Composition

- Place the principal subject **in the centre or right half of the frame, never on the left**.
  Centre-right is the default. The left side can carry landscape, approach, weather, context,
  or breathing room.
- Keep the face, head, or defining feature away from the outer 15 percent of the frame. Hero
  and card layouts crop with `object-fit: cover`, so the subject must survive a centred crop.
- Vary framing across a batch: establishing wide shot, low wide angle, medium environmental
  portrait, ground-level action, elevated view, waterline view, and restrained close shot.
- Use posture to tell the story. Prefer kneeling, seated, crouched, wading, working, turning,
  watching, climbing, or interacting over repeated upright figures facing the camera.
- Secondary figures should support the named legend and remain visually subordinate. Avoid
  crowding every image with witnesses.
- Sacred-site images may make the site itself the principal subject. Place its defining
  structure or landform centre or right and show the specific associated event where useful.

## People and dignity

- Named figures may have clearly visible faces when that helps distinguish them, but the
  image is an interpretation, not a claimed likeness. Avoid glamour poses and camera-aware
  expressions.
- Historical victims, accused witches, and people linked to tragedy must be portrayed with
  dignity. Prefer the human event that created the legend over execution, torture, or lurid
  horror.
- Specify identity deliberately: age, build, face shape, hair, skin tone, occupation, dress,
  and posture. Do not allow every hero to become the same tall bearded man or every witch the
  same thin hooded woman.
- Avoid costume shorthand: pointed witch hats, generic wizard robes, horned helmets, fantasy
  armour, and spotless Robin Hood outfits unless a sourced tradition genuinely requires it.

## Variety control

Treat variety as a batch-level requirement, not an afterthought. Before prompting, give each
image a distinct combination across these axes:

| Axis | Examples |
| --- | --- |
| Subject form | human, pair, crowd, quadruped, serpent, birdlike, amphibious, spectral, site |
| Human identity | child, young adult, middle-aged, elderly; short, tall, broad, wiry, disabled |
| Surface and dress | fur, scales, feathers, wet skin; workwear, court dress, fisher wool, armour |
| Posture | seated, crouched, prone, walking, riding, swimming, emerging, coiled, flying |
| Lens and distance | low wide, long lens, elevated wide, medium environmental, waterline |
| Light | dawn, hard overcast, twilight, moonlight, storm break, firelight, winter glare |
| Palette | slate and rust, peat and green, chalk and blue, black and amber, mist and ochre |
| Setting | coast, loch, marsh, mountain, road, cottage, market, ruin, forest, open sea |

Do not repeat the same dominant silhouette, facial type, costume, camera height, or palette in
adjacent images. For groups of related small creatures, change anatomy as well as accessories:
body proportions, limb length, head shape, ears, skin or coat, age, posture, and behaviour.
Changing only clothing or background does not create sufficient variety.

## Category direction

- **Dragons and beasts:** Follow the description even when biologically impossible. Vary
  serpentine, heavy-bodied, winged, aquatic, mammalian, avian, and hybrid anatomy. Show scale
  through terrain or interaction, not by repeating the same roaring three-quarter pose.
- **Legendary figures, pirates, and deities:** Build a distinct person and depict a specific
  deed. Vary gender, age, build, culture, occupation, expression, and social setting.
- **Giants:** Show environmental scale, but vary body type, activity, camera distance, and
  relationship to the landscape. A giant need not always stand on a ridge.
- **Ghosts:** Show the apparition or haunting action. Vary translucence, material presence,
  number of spirits, period, interior or exterior, and emotional tone. Avoid identical pale
  women in long dresses.
- **Fae and spirits:** Follow local descriptions rather than defaulting to winged fairies or
  goblin-like humanoids. Vary scale, anatomy, age, texture, movement, and social behaviour.
- **Witches:** Distinguish cunning folk, healers, accused historical people, storm-witches,
  fairy seers, and folkloric hags. Avoid pointed hats, repeated cauldrons, and repeated occult
  hand gestures.
- **Water spirits and monsters:** Show the being or event in, under, or emerging from water.
  Vary water type, camera position, anatomy, visibility, scale, weather, and relationship to
  boats or shore.
- **Sacred sites:** Show the actual defining feature and its real landscape character. Avoid
  generic standing stones, empty ruins, or invented architecture when the site is documented.

## Technical specification

- **Aspect ratio:** near-exact 16:9 landscape. Existing accepted masters are `1600x900` and
  `1672x941`; do not introduce square or portrait heroes.
- **Format:** JPEG, quality about 82, optimised and progressive.
- **Filename:** `legend-images/{legend-slug}-hero.jpg`, using the same `slugify()` rules as
  `generate_pages.py`.
- **Derived files:** `generate_pages.py` creates WebP heroes and 800-pixel card thumbnails.
  Do not create those by hand.
- **Metadata:** add `image`, literal scene `alt`, and a short factual `caption` under the exact
  legend name in `legend_pages.json`.

Alt text describes what is visible. It should not say only "illustration of...". Captions may
use the pattern "A visual interpretation of..." and should identify the tradition or event.

## Preflight and non-overwrite rule

Before generating, audit all three sources of truth:

1. The legend record in `legends.json`.
2. Its exact-name entry and `image` path in `legend_pages.json`.
3. The actual file under `legend-images/` and the slug in `legend-images/manifest.json`.

The page's real image path and file existence are authoritative. Do not assume a guessed slug
means an image is missing. Also check the proposed target filename directly before generation.

Never overwrite an existing hero unless replacement was explicitly requested. For a correction,
write a versioned sibling such as `name-hero-v2.jpg`, inspect it, then update metadata to point to
the new file. Leave the original in place until a separate cleanup is approved.

## Prompt template

```text
Use case: historical-scene or stylized-concept
Asset type: folklore atlas legend-page hero, cinematic 16:9 landscape
Primary request: "{exact legend name}" - depict {specific deed, encounter, or haunting}
Scene/backdrop: {real region, period, terrain, architecture, and weather}
Subject: {legend itself; precise anatomy or age, build, face, hair, dress, posture}
Style/medium: cinematic photorealism, grounded documentary still, tactile physical detail
Composition/framing: {distinct lens and distance}; subject centre or right, never left;
  defining features protected from edge crops; contextual space on left
Lighting/mood: {specific natural light and emotional register}
Color palette: {muted base plus one controlled accent}
Constraints: period-plausible; no modern objects; no text, logo, border, or watermark;
  no generic category shorthand; {legend-specific avoid list}
```

Write each prompt independently. Do not paste the same character description, composition, or
lighting block into every item in a batch.

## Quality review

Inspect every full image and the batch contact sheet before wiring or committing it. Confirm:

- The exact legend is visible and recognisable.
- The principal subject is centre or right and survives a centred 16:9 crop.
- Anatomy, hands, faces, equipment, architecture, and period details are plausible.
- No text, watermark, duplicated body parts, modern object, or unintended stock-fantasy trope.
- The batch varies identity, silhouette, posture, camera, light, palette, and setting.
- Accused or tragic historical people are treated with dignity.
- The proposed path did not exist before the batch.

Then update `legend_pages.json`, run `generate_pages.py`, and validate that every legend has an
existing referenced file and that the regenerated manifest contains its slug.

## AI disclosure

Hero and collection pages automatically render the fixed wording: "Illustration created with
the assistance of generative AI." Do not add disclosure text inside the image or paraphrase it
per entry.

That wording is now the default rather than the only option: it renders when an entry has no
`credit` block, which is every entry in the current library. An entry that carries one prints its
real provenance instead. See Non-AI imagery below.

## Non-AI imagery

Phase 3 Stage 4 opens the library to place photography, historic maps, archival illustration,
public-domain engravings and source-document excerpts. The point is not variety for its own
sake. The site claims entries are rooted in real places and real research, and an image library
that is entirely synthetic quietly argues the opposite.

Nothing about the existing AI library changes. It stays, it stays labelled, and the guidance
above still governs every generated image.

### The credit block

Provenance is data, not an assumption. Add an optional `credit` object to the entry in
`legend_pages.json`, or to the collection in `collections.json`:

```json
"credit": {
  "medium":  "engraving",
  "creator": "Gustave Dore",
  "source":  "Internet Archive",
  "licence": "Public domain",
  "url":     "https://archive.org/details/..."
}
```

- **`medium`** is one of `photograph`, `engraving`, `map`, `document`, `painting`,
  `illustration`, or `ai`. Anything else is printed capitalised, so an unlisted medium degrades
  to something sensible rather than breaking.
- **`licence`** is required on everything that is not `ai`. The build **raises** without it. An
  unlicensed third-party image is the one mistake here whose consequences go beyond a
  wrong-looking page, so it stops the build rather than publishing quietly.
- **`creator`**, **`source`** and **`url`** are optional. A `url` is only linked when it is
  `http` or `https`.
- **No `credit` block means AI-generated**, which is what all 712 current entries are. Nothing
  needs backfilling.

The rendered line replaces the AI disclosure, so a photograph reads
`Photograph by Jane Doe · National Library of Scotland · CC BY 4.0` and never claims to be
generated. `hero_credit` on a collection still works and is printed in front of the credit line.

### Licence rules

- **Record the licence for the specific item, not the institution.** Holdings are mixed. A
  library being old does not make a given scan public domain, and several of the archives below
  serve public-domain originals under their own terms for the digitisation.
- **Reproduce the licence's own wording** in the `licence` field. "Public domain", "CC BY 4.0",
  "CC BY-SA 4.0", "CC BY-NC 4.0" and so on. Do not summarise or soften it.
- **Attribute whatever the licence asks for**, in `creator` and `source`. Where a licence
  demands a specific credit string, put that string in verbatim rather than reformatting it.
- **`NC` licences are usable here** while the site takes no payment for content. Ko-fi support
  is a donation rather than a sale, but if that ever changes, the `NC` items have to be
  re-checked. Worth knowing before leaning on them heavily.
- **If the rights are unclear, do not use it.** There is a working AI image already.

### Where to look

These are already in the site's own source-tier table as heritage or primary, so they are
sources it cites for text and can reasonably cite for images:

- `archive.org` and `babel.hathitrust.org` for scanned nineteenth-century folklore volumes,
  which is where most usable engravings are.
- `books.google.com` for the same, though the rights position on individual scans is messier.
- `canmore.org.uk` and `historicenvironment.scot` for Scottish sites and monuments.
- `british-history.ac.uk` and `celt.ucc.ie` for source-document excerpts.
- `duchas.ie` for the Irish folklore collection, including manuscript pages.

Check the terms per item at each of them.

### What is still an editorial call

The mechanism is built and enforced; the direction is not, and should not be decided by
whoever happens to be adding an image that day.

- **What proportion, and how fast.** A handful of well-chosen archival images does more for the
  research claim than a scattering of weak ones.
- **Which entries go first.** The obvious candidates are entries where a real artefact exists:
  a carved bench-end, a standing stone, a manuscript page, a named person with a period
  portrait.
- **Whether medium should follow category or period.** Maps suit place entries, engravings suit
  nineteenth-century collected tales, photographs suit extant sites. That is a plausible rule,
  not a decided one.
- **Whether a real image always beats a generated one.** It usually will for a site that exists
  and a person who was drawn from life. It will not for a creature nobody has photographed.

Until those are settled, treat every non-AI image as a deliberate one-off rather than the start
of a rollout.
