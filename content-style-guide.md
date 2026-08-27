# Legend page writing style guide

Working notes for writing and rewriting legend `detail` text in `legends.json`.
Distilled from three sources plus the site's own best existing pages, after the
Robin Hood entry was flagged as reading "very AI" (2026-07-20).

Sources:
- [Cambridge International — Writing an Article](https://learning.cambridgeinternational.org/classroom/pluginfile.php/218996/mod_label/intro/Writing_an_article.pdf)
- [LinkedIn — Structure of an Article: A Guide to Effective Writing](https://www.linkedin.com/pulse/structure-article-guide-effective-writing-aneela-majeed-yt1ef)
- [BBC Bitesize — Writing to inform, explain and describe](https://www.bbc.co.uk/bitesize/guides/zwt3rdm/revision/4)

## The core rule: narrate, don't comment

The single biggest tell in the flagged Robin Hood draft wasn't a word choice, it
was a stance. The opening talked *about* the legend ("has haunted the English
imagination for at least seven centuries... belongs to the land as much as any
named king") instead of just telling it. That meta-commentary move — stepping
back to remark on how long people have believed something, how enduring it is,
what it "represents" — is the clearest AI tell there is, because it's a move a
real folklorist doesn't make in the first sentence. They just tell you who the
figure is and what they did.

Compare the site's own best openings, which never do this:
- *"Black Shuck... has prowled the lonely lanes, marshes and shingle of Norfolk
  and Suffolk for centuries."* — a concrete action, not a claim about culture.
- *"Arthur is the once and future king of British legend: a war-leader who...
  united the Britons and held back the advancing Saxons."* — identity and
  action in sentence one.

**Rule: the first sentence states who/what the figure is and does. Cultural
"this story has lasted for centuries" framing, if used at all, comes later,
earned by facts already given — never as the opening move.**

## Don't use em dashes

Every AI drafting pass leans hard on em dashes to bolt a parenthetical onto a
sentence instead of just writing two sentences, or a comma, or parentheses.
It's readable in small doses but the tell is the *frequency* — real prose
varies its punctuation, and this site's content should read as if a person
wrote it, not as if it were assembled out of parenthetical asides.

**Rule: don't use em dashes at all. Rewrite with commas or sentence breaks
instead, as the sentence calls for. Prefer, in this order:**
- A full stop, when the second half is really its own sentence.
- A comma, for a short appositive or aside.
- Parentheses, when the aside is a genuine side-note that would otherwise
  interrupt the sentence's flow.
- A colon, only when the second half genuinely explains or lists what the
  first half named — never as a general-purpose dash replacement.

This is a hard rule, not a frequency cap. A single well-placed em dash is
still the same tell as three; if a sentence seems to need one, that's a sign
the sentence needs restructuring, not that this is the rare exception. The
only place an em dash may survive untouched is inside a direct quotation,
where altering the original text would misrepresent the source.

**Don't just trade the dash tell for a colon tell.** A 2026-08-07 re-read of
pages that had already been through a dash-cutting pass found the same
frequency problem had reappeared one punctuation mark over: paragraphs with
a colon in nearly every sentence, doing the exact job the em dashes used to
do. Colon overuse is exactly as much of a tell as em-dash overuse. If a
paragraph is gaining colons as it loses dashes, that's not a fix, it's the
same crutch under a new name — reach for the full stop and the comma first,
and use a colon only where it's structurally called for (a list, a label,
an introduced quote), not as a punctuation-of-convenience.

### Cycle 3: this is a remediation target, not just a drafting rule

The rule above governs new sentences, and new sentences have been fine. The
back catalogue has not. This rule was declared done on 2026-08-07 and again on
2026-08-12, and was wrong both times, because a pass over *some pages* was
reported as a pass over *the dataset*. Cycle 2 closed with the dataset still
carrying dashes, so Cycle 3 owns clearing them.

**Measured baseline, 2026-08-23** (`python scripts/dash_audit.py`):

| | count |
|---|---:|
| dash characters in prose fields | 743 |
| field values containing at least one | 429 |
| entries affected | 293 of 709 |

By field: `summary` 144, `detail` 146, `earliest_record` 59,
`historical_setting` 28, `period` 19, `cultural_tradition` 6, `origin_date` 2.

**Three things that make this go wrong, so plan around them:**

1. **Fix the entry, never the page.** `legends.json` is the source and the HTML
   is downstream of it. Editing a generated page means the next
   `python generate_pages.py` puts the dash straight back, and the fix looks
   done for exactly as long as nobody rebuilds.
2. **Don't count rendered pages.** A `summary` dash is emitted into
   `description`, `og:description`, `twitter:description` and the body, so
   scanning HTML multiplies every dash by three or four and makes the job look
   roughly three times bigger than it is. Count fields in `legends.json`.
3. **Leave numeric ranges alone.** 25 values hold a date range
   ("1560s-1576", "c. 1196-98", "AD 60-61"). A range wants a hyphen, not a
   rewrite, and `dash_audit.py` already separates these out. They are not
   failures and should not be counted as progress either.

**Definition of done, and it is checkable:**

```
python scripts/dash_audit.py --strict
```

Exit 0 means clear. Any entry an enhancement run touches must come back
dash-clean across all seven prose fields, not only the field being enhanced,
otherwise the count drifts back up between sweeps. Do not report this rule as
satisfied on the strength of a spot-check: run the script and paste the total.

## Other AI tropes to avoid

- "stands as a testament to...", "is a testament to...", "in the annals of..."
- "not just X, but Y" / "more than just X"
- "rich tapestry", "steeped in", "woven into the fabric of"
- Triadic rhythm abused as a crutch ("sometimes X, sometimes Y, always Z")
  used more than once per page
- Present-tense scene-setting throat-clearing before the actual subject shows up

## Structure (from the Cambridge/BBC/LinkedIn guides, adapted for legend pages)

1. **Opening** — who/what the figure or place is, and the one thing they're
   known for, in the first sentence. A concrete fact, date, or action as the
   hook, not an abstraction.
2. **Middle** — develop the story: the specific events, the named details
   (place, object, other characters), what makes this version of the legend
   distinct. Vary sentence length and structure paragraph to paragraph so nothing
   reads like a template being filled in.
3. **End** — a grounding, present-tense detail if one exists (a place you can
   still visit, an object that still exists, a tradition still practised).
   This is already the site's strongest recurring device — keep using it.

Keep paragraphs short (this is a folklore reference page, not an essay) and
avoid repeating the same fact in two different paragraphs (the original Robin
Hood draft repeated "skilled archer... robs from the rich... corrupt sheriff"
almost verbatim in paragraphs one and two).


## Assigning `period_slug`

`period_slug` is a controlled field on every legend. It holds exactly one slug
from `periods.json` or nothing at all, and it decides which Explore Through Time
page a legend appears on.

**It means when the legend is SET. Never when it was written down.**

That distinction is the whole point of the field, because the older free-text
`period` field mixes the two and cannot be normalised into this one. Two worked
examples, both real:

- Dinas Emrys carries `period` = "Early medieval Wales (textual composition, 9th
  century)". Every word of that is about the manuscript. The story is Vortigern
  and Merlin, so the slug is `sub-roman-britain`.
- Glastonbury Holy Thorn carries `period` = "High Medieval England
  (Joseph-as-founder tradition, 12th century); the thorn-specific legend
  attested from the 17th century". Again all record. The story narrates Joseph
  of Arimathea, so the slug is `roman-britain`.

Read the `summary` and `detail`, not the `period` field. The record axis already
has a home in `earliest_record`, which renders on the legend page directly
beneath the period.

### The ladder

Work down it. The first rule that yields an answer wins.

1. **A datable event or person in the story.** Use the period of the event, not
   of the telling. Dick Turpin is `georgian-britain`. The Witches of Belvoir
   (tried 1619) are `stuart-britain`. The Kilkenny witch trial (1324) is
   `medieval-britain`. A legendary figure counts if the tradition places them
   in time: Arthur is `sub-roman-britain` whether or not he existed, because
   that is where the tradition puts him.

2. **A monument the tradition explains.** No datable event, but the legend
   exists to account for a physical feature whose date is known, and the story
   is about that feature's making or its makers. Wayland's Smithy is
   `prehistoric-britain`, Chun Quoit is `bronze-age`. The test is strict: a
   Victorian ghost merely *seen at* a stone circle is not Bronze Age. If the
   monument is only the stage, this rule does not apply, so fall through.

3. **One defining text, and no setting of its own.** The legend's earliest and
   defining form is a specific literary work and the story has no independent
   setting. Sir Gawain and the Green Knight is `medieval-britain`. This is the
   only place a text's date is allowed, and only because for a genuine literary
   creation the text date *is* the setting date. It must never be used for a
   text that merely records an older oral belief. Getting that wrong is exactly
   the misfile this field exists to prevent.

4. **Otherwise, no `period_slug`.** Omit the field. Baobhan Sith, Brownie,
   Each-Uisge and Redcap are undated oral tradition and belong on no period
   page. An absent value is a correct, finished answer, not a gap for a later
   pass to fill. Do not reach for `modern-folklore` to avoid leaving it blank.

### Boundaries and the two deliberate overlaps

Every period carries `bounds` and a `disambiguation` note in `periods.json`.
Read the note before assigning. The three that catch people out:

- **793 to 1066** is covered by both `early-medieval-britain` and `viking-age`.
  Use `viking-age` only for Norse raiders, settlers or Norse-derived belief. In
  Orkney, Shetland, the Hebrides, the Isle of Man and Norse Ireland it is the
  default for that window instead.
- **`norman-britain` is 1066 to 1154 only**, the Conquest and its aftermath.
  The rest of the Middle Ages is `medieval-britain`.
- **`prehistoric-britain` is Mesolithic and Neolithic only.** A round barrow is
  `bronze-age` and a hillfort is `iron-age`. What fills the prehistoric page is
  long barrows, chambered tombs and causewayed enclosures.

`victorian-britain` and `edwardian-britain` need the same care from the other
direction. Almost every British and Irish legend was written down by a Victorian
or Edwardian folklorist, and none of that is grounds for either page. Only a
legend genuinely set in 1837 to 1914 belongs there.

### The negative test

Delete every clause about being recorded, published, attested, documented,
collected, first noted or printed. Decide from what is left. If nothing is left,
the answer is rule 4.
