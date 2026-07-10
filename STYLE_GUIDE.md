# Folklore Finder Site Style Guide

This guide defines the shared site chrome and page-heading rules. Treat these as implementation requirements, not loose inspiration.

## Canonical Site Chrome

Use the Home page footer brown for every top navigation bar and every footer:

- Bar background: `#1a0e06`
- Piping: a 3px gold/rust line at the top of the nav and a 1px gold/rust divider at the bottom of the nav
- Footer piping: a 1px gold/rust divider at the top of the footer
- Primary text on dark bars: `rgba(242,232,213,0.78)`
- Footer/link text on dark bars: `rgba(246,241,230,.78)` and `rgba(246,241,230,.9)`
- Active nav link: `#c4622a`

The shared CSS source of truth is `folklorefinder.css`. Generated browse pages mirror the same rules in `TOPNAV_CSS` inside `generate_pages.py`. Individual legend pages mirror the same rules in `legend-page.css`.

## Top Navigation

Every page except the Home page must show the brand lockup at the far left:

```html
<a class="topnav-brand" href="./" aria-label="Folklore Finder home">
  <img class="topnav-emblem" src="green-man.png" alt="Green Man"/>
  <span class="topnav-title">Folklore Finder</span>
</a>
```

Use root-relative paths on root-hosted absolute pages such as `404.html`:

```html
<a class="topnav-brand" href="/" aria-label="Folklore Finder home">
  <img class="topnav-emblem" src="/green-man.png" alt="Green Man"/>
  <span class="topnav-title">Folklore Finder</span>
</a>
```

Brand lockup rules:

- Logo size: `40px` by `40px`
- Logo-title gap: `11px`
- Brand title font: `Marcellus`
- Brand title size: `clamp(18px, 2.1vw, 23px)`
- Brand title weight: `400`
- Brand title letter spacing: `0.055em`
- Do not add decorative stars/glyphs before or after the nav title.

Nav links:

- Font: `Marcellus`
- Size: `12px`
- Letter spacing: `.08em`
- Text transform: uppercase
- Padding: `6px 14px`
- Border radius: `3px`

Mobile nav:

- At `max-width: 640px`, keep the top nav as one horizontal row.
- Use `flex-wrap: nowrap`, `overflow-x: auto`, and `scrollbar-width: none`.
- Each nav link should use `flex: 0 0 auto` and `white-space: nowrap`.
- Do not wrap the nav links onto multiple rows on mobile.

The Home page keeps its current nav without the brand lockup because the full Folklore Finder title and logo are already the hero identity.

## Map Page Exception

The Map page must match the same nav color, title/logo sizing, nav link styling, and footer styling as the rest of the site.

Allowed difference:

- The day/night toggle remains in the top-right header controls.

Not allowed:

- Do not show the subtitle `An atlas of myths, legends, & stories` in the Map page header.
- Do not use a different bottom banner color.
- Do not put map attribution or bug-report buttons in the site footer. Map attribution should live with the map controls.

## Footer

Every public page footer must use this exact content and link set:

```html
<footer>Folklore Finder &nbsp;&#183;&nbsp; An atlas of myths, legends, &amp; stories &nbsp;&#183;&nbsp; &copy; EditionTree &nbsp;&#183;&nbsp; <a href="https://folklorefinder.uk/about">About</a> &nbsp;&#183;&nbsp; <a href="https://folklorefinder.uk/updates">Updates</a> &nbsp;&#183;&nbsp; <a href="https://ko-fi.com/folklorefinder" target="_blank" rel="noopener">Ko-fi</a> &nbsp;&#183;&nbsp; <a href="https://folklorefinder.uk/privacy">Privacy</a></footer>
```

Do not add a Home link. Do not remove About or Updates. Do not add a coffee icon before Ko-fi.

## Interior Page Headings

Interior page hero headings such as About, My Archive, Privacy, Achievements, and What's New should use the same scale:

```css
font-family: 'Marcellus', serif;
font-size: clamp(42px, 6vw, 74px);
font-weight: 400;
line-height: .98;
letter-spacing: .025em;
```

Do not make the What's New heading smaller than the other interior page headings.

## Generated Pages

When changing shared chrome, update all relevant sources:

- `folklorefinder.css` for root static pages
- `legend-page.css` for individual legend pages
- `generate_pages.py` for generated browse, collection, period, region, and legend output
- `map.html` for the interactive map's embedded header/footer styles

After changes to generated page chrome, run `python generate_pages.py` so generated HTML is refreshed.
