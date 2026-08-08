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

If real photography is introduced later, licensing and photographer credit must be recorded,
and the current automatic AI label will need a non-AI metadata flag before publication.
