# Founder note

This file is the source for the "Why this exists" section on the About page.
Edit the prose below, then run:

    python generate_pages.py

and the About page is rebuilt from it. Nothing here needs to go through Claude.

---

## How it works

- **`PUBLISH:`** must be `yes` before the section appears on the site. It ships as
  `no` so nothing goes live until you have actually written it. There is no
  placeholder text on the live site in the meantime; the section simply is not there.
- **`HEADING:`** is the small caps label above the section. Keep it short.
- **`CREDIT:`** is an optional single line printed small and quiet at the end,
  for the EditionTree question. Leave it blank to print nothing.
- Everything after the `---` divider under **Note** is the note itself.

Formatting you can use in the note: blank lines separate paragraphs, `*single
asterisks*` italicise, `**double**` embolden, and `[text](https://example.com)`
makes a link. Anything else is printed as plain text, so you cannot break the
page by writing normally.

Two house rules the rest of the site follows, worth keeping here:

- **No em dashes or en dashes.** Use a full stop or a comma. This is a hard rule
  across the site, and the build will warn you if any slip in.
- Write it the way you would say it out loud. The rest of the site is deliberately
  plain, and a founder note is the one place first person is allowed, so it will
  stand out for the right reasons if it sounds like a person.

## Prompts, if a blank page is unhelpful

You do not have to answer these, and you should not answer all of them. They are
here only to give you something to push against. Three or four short paragraphs
is plenty; the About page already explains what the site does, so this only has
to say why.

- What made you start? A specific legend, a place, a walk, a book, an irritation
  with what was already online.
- What were you looking for that did not exist?
- Why the insistence on sourcing? The site makes a real claim there
  ("Researched, not repeated") and this is the natural place to say where that
  came from.
- What do you want someone to do after reading an entry?
- What is it not? Worth saying if you have a clear view.

Avoid anything you would not want a stranger to know. No location beyond the
regional, no employer, no family detail.

## The EditionTree question

The footer currently reads `© EditionTree`, which is unexplained anywhere on the
site. Two ways to resolve it, from the Phase 3 roadmap:

1. **Name it plainly.** Put something like "Folklore Finder is an EditionTree
   project" in `CREDIT:` below, so the name has a stated relationship to the site.
2. **Keep it a quiet publisher credit.** Leave `CREDIT:` blank and the footer
   line alone. It reads as a copyright holder and nothing more.

If you want the footer itself changed rather than a line here, say so and it is a
mechanical change across every page.

---

PUBLISH: no
HEADING: Why this exists
CREDIT:

## Note

Write here. Delete this line first.
