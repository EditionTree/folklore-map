# Folklore Finder — Phase 3.0

**Consolidate, harden, market. No new large feature areas.**

Sources fused into this plan: the red-team, marketing and web-development reviews (2026-08-21),
the code review below (run 2026-08-21 against commit `5bb493a2`), and outstanding Cycle 2
content work carried over from [`project_current_state`](../.claude/projects/).

---

## Part 1 — Code review

Run over the working tree at `5bb493a2`. Findings are ordered by severity, and each one names
the file. Where a claim needed proof it was verified against the live site or the live Supabase
project rather than inferred from the source.

### S1 — Confirmed, user-facing, fix first

**1.1 The site's own security header breaks "Find folklore near me".**
`_headers:5` sends `Permissions-Policy: geolocation=()`. An empty allowlist disables the
Geolocation API for the document entirely. Verified live:

```
$ curl -sI https://folklorefinder.uk/ | grep -i permissions-policy
permissions-policy: camera=(), microphone=(), geolocation=()
```

The failure mode is worse than a dead button. `index.html:1135` sets the status text to
*"Requesting your location. Look for a permission prompt from your browser"*, no prompt can
appear, and the error branch at `index.html:1170` reports **"Location access was declined, so we
can't find your nearest legend."** The site invites the user to act, blocks the action itself,
then blames the user for refusing. This is the homepage's primary call to action.

Fix: `geolocation=(self)`.

**1.2 The Privacy Notice is materially inaccurate.**
`privacy.html` states: *"We do not require accounts, and we do not ask for your name or email
anywhere on the site."* The feedback form collects `contact_email`, which
`supabase/functions/submit-feedback/index.ts` sanitises to 320 characters and writes to
`public.feedback`. The notice never mentions the feedback table at all.

It is also silent on first-party telemetry. The Analytics section describes only Cloudflare Web
Analytics and says no personal data is collected. In fact every page posts to `submit-event`,
which writes `event_type`, `legend_name`, `collection_slug`, `period_slug`, `guide_id`,
`item_id`, `referring_page` and a pseudonymous `session_id` into `public.analytics_events` with
no stated retention.

An affirmative denial that email is collected, plus an undisclosed processing operation, is a
UK GDPR Article 13 transparency failure — not a wording nitpick. Highest non-technical priority.

**1.3 Analytics and feedback have never worked. Both are silently failing in production.**
This began as "harden the event endpoint" and turned out to be a live outage.

**The evidence.** `public.analytics_events` holds **0 rows**. `public.feedback` holds **0 rows**.
Function logs for the last 24 hours alone contain **332 identical failures**:

```
DB insert error: {
  code: "42501",
  message: "permission denied for table analytics_events",
  hint: "Grant the required privileges to the current role with:
         GRANT INSERT ON public.analytics_events TO service_role;"
}
```

**Root cause.** `service_role` grants, by table:

| table | service_role grants | rows | working? |
|---|---|---:|---|
| `analytics_events` | REFERENCES, TRIGGER, TRUNCATE | 0 | **no — no INSERT** |
| `feedback` | REFERENCES, TRIGGER, TRUNCATE | 0 | **no — no INSERT** |
| `bug_reports` | INSERT, SELECT, UPDATE, … | 1 | yes |
| `legend_submissions` | INSERT, SELECT, UPDATE, … | 0 | yes (genuinely no submissions) |

`20260707100000_add_analytics_events.sql` and `20260706120000_add_feedback.sql` both end with
`revoke all on <table> from anon, authenticated;` and never grant anything to `service_role`.
`bug_reports` and `legend_submissions` were created by hand in the dashboard — which grants
`service_role` automatically — so they work. The feedback migration's own comment says it
mirrors "the same lockdown pattern as bug_reports/legend_submissions", but it reproduced the
revoke half of that pattern without the grant half that the dashboard had supplied invisibly.
This is the RLS-versus-GRANT distinction recorded in `project_folklore_map`, hit from the
opposite direction: service role bypasses RLS, but it does **not** bypass table grants.

**Impact.**

- **Analytics: broken since the function was deployed, 2026-07-07** — roughly six weeks. Every
  page view, collection view, period view, achievement unlock and journal click since then is
  gone. 332 failures in 24h means real traffic is hitting it. There is no data to recover.
- **Feedback: broken since 2026-07-06.** This is the serious one. Every visitor who wrote
  feedback got *"Feedback could not be saved — please try again"*, retried, and failed again.
  Those messages — including any corrections to legends, which is the exact contribution the
  site asks for — were never stored anywhere.

**Why nobody noticed.** `submit-event` returns `200 {success:true}` regardless of whether the
insert succeeded, and the client calls `.catch(() => {})`, which does not fire on a non-2xx
response anyway. A six-week total outage produced no user-visible symptom and no alert. The
"returns 200 on failure" design is not a code-quality nitpick — it is the direct reason this
went undetected for six weeks. `submit-feedback` does correctly return 500, but with no
volume alerting nobody saw those either.

**Fix:**

```sql
grant insert on public.analytics_events to service_role;
grant insert, select, update on public.feedback to service_role;
```

Then re-probe both endpoints and confirm a row lands, before anything else in this section.

### S2 — Security weaknesses with no confirmed exploit

**2.1 `anon` holds destructive privileges on `public.legends`.**
Verified against the live project:

| table | RLS | anon grants |
|---|---|---|
| `analytics_events` | on | none |
| `bug_reports` | on | none |
| `feedback` | on | none |
| `legend_submissions` | on | none |
| **`legends`** | on | **SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES** |

The only policy on `legends` is `Public read access` (`SELECT`, `qual: true`). Writes are
therefore denied — RLS defaults to deny where no policy exists, so the INSERT/UPDATE/DELETE
grants are inert.

**TRUNCATE is the exception. Postgres does not apply row-level security to TRUNCATE** — it is a
table-level privilege, so RLS is not the control here. The only thing standing between a
publicly-published anon key and an emptied `legends` table is that PostgREST exposes no verb
that reaches TRUNCATE. That is an accident of the API surface, not a deliberate control.

Fix: `REVOKE ALL ON public.legends FROM anon, authenticated;` then
`GRANT SELECT ON public.legends TO anon;`. Do this before the `public_legends` view work, not
as part of it.

**2.2 Once it works, `submit-event` is unauthenticated, unvalidated and unlimited.**
Verified reachable with no `Authorization` or `apikey` header (`verify_jwt: false`), so a plain
curl reaches it. It checks that `event_type` is on an allowlist and nothing else: no rate limit,
no body-size cap, no per-event-type field validation (an `achievement_unlocked` event may carry
a `period_slug`), and it inserts with the service-role key. Anyone can forge the record and
drive up invocation cost. These remain the right fixes — but they are now **preconditions for
switching the pipeline on**, not repairs to a running system. Do them in the same change as the
grant, so the endpoint is never briefly both working and unprotected.

**2.2a Two allowlist defects that will still bite after the grant is fixed.**

- `index.html:1195` fires `trackEvent('home_cta_click', …)`. **`home_cta_click` is not in the
  edge function's `EVENT_TYPES`, nor in the table's `event_type` CHECK constraint.** It will 400
  and be dropped even once permissions are fixed. Homepage CTA tracking — the exact data needed
  to make the Stage 5 hierarchy decisions — is doubly broken. Its `cta` field is also not
  destructured by the function, so it would be discarded regardless.
- Four allowlisted types are fired by nothing: `guide_viewed`, `guide_downloaded`,
  `kofi_link_clicked`, `product_clicked`. Either wire them up or drop them.
- The allowlist is duplicated between the function and the table's CHECK constraint, so every
  event type must be changed in two places. Pick one as authoritative.

**Do not let the Quality workstream depend on this data.** The sourcing audit's "entries
receiving the most search traffic" priority cannot be answered from `analytics_events` — there
is nothing in it. Use Search Console until the pipeline has been fixed and has accumulated
history.

**2.3 `submit-legend` has an unhandled crash path reachable before Turnstile.**
`supabase/functions/submit-legend/index.ts:44` defines `sanitise` as `s.trim().slice(...)`,
missing the `String(s ?? '')` guard the other three functions use. Line 72 then calls
`!legend_name?.trim()` directly on the parsed JSON value. A body of
`{"legend_name": 1, "region": "x", ...}` throws `TypeError: legend_name.trim is not a function`
inside the handler and returns an unhandled 500. Low impact, trivially fixed, but it is a crash
an unauthenticated caller can trigger before the Turnstile check runs.

**2.4 Turnstile executes on page load for every visitor, not on form interaction.**
`map.html:47` loads `api.js` with no `render=explicit`, and the widgets at `map.html:983`
(bug report) and `map.html:1012` (submit legend) sit in the static markup of hidden modals.
Implicit rendering scans the DOM on script load and renders every `.cf-turnstile` match
regardless of container visibility — so **every map visitor runs two Cloudflare challenges** for
forms most of them never open. Same pattern at `updates.html:252`.

The `turnstile.reset()` calls are the evidence: if the widgets were not already rendered at page
load, resetting them on modal open would be a no-op and the first submission would carry no
token.

Fix: load `api.js?render=explicit` and call `turnstile.render()` inside `openBugReport()`,
`openSubmitLegend()` and `openFeedback()`, where the `reset()` calls already live.
`data-appearance="interaction-only"` is the cheaper half-measure but still loads and initialises
the script for everyone. Worth prioritising on `map.html`, already the heaviest page on the site.

**Token lifecycle is already handled correctly — keep it.** Tokens expire after 300s and are
single-use. The code resets on modal open (`map.html:1918`, `map.html:2025`, `updates.html:385`)
and after both success and failure (`map.html:1985`, `map.html:2106`). All three forms are
modals, so there is no path where a visitor sits on a stale rendered widget and hits a
`timeout-or-duplicate` 403.

**2.5 Optional: pass `remoteip` to siteverify.** All three endpoints append only `secret` and
`response`. Adding `req.headers.get('CF-Connecting-IP')` tightens the check slightly. Weigh it
against the feedback form's own copy — *"We don't log your IP address"* — which this does not
contradict (Cloudflare already sees the IP as the CDN, and siteverify is not logging), but which
it makes harder to explain. Marginal gain; dropping it is a defensible call.

### S3 — Performance

**3.1 Cache-busting defeats caching on the two largest JSON payloads.**
`map.html:1865` and `map.html:1870`:

```js
return fetch('legends.json?v=' + Date.now())
fetch('legend_pages.json?v=' + Date.now())
```

`legends.json` is 2.1 MB and `legend_pages.json` is 499 KB. `Date.now()` makes every request a
unique URL, so neither the browser cache nor Cloudflare's edge cache can ever serve a repeat
visit. `legend_pages.json` is fetched unconditionally on every single map load — it is not the
fallback path, it supplies popup artwork. The site already has a working manual `?v=` discipline
for CSS and JS; these two calls simply never adopted it.

**3.2 A bookmark click rebuilds the entire map.**
`map.html:1246`, inside `toggleBookmark()`:

```js
markers.forEach(marker => marker.setPopupContent(buildPopup(marker._legendData)));
```

Every bookmark toggle re-runs `buildPopup()` — string concatenation, HTML escaping, a
`FEATURED_PAGES` lookup — for all 709 markers, then calls `buildFilters()`, then rebuilds the
sidebar. One click on a star does O(n) work across the whole dataset. Only the clicked marker's
popup needs updating.

**3.3 The entries panel builds ~4,200 DOM nodes on every filter change.**
`buildSidebarList()` (`map.html:1757`) constructs six elements per legend plus an `item.onclick`
closure, for every visible entry, on every filter change and every bookmark toggle. At 709
entries that is roughly 4,200 nodes and 709 closures. This is the specific thing that breaks
first as the archive grows — test it at 1,500 and 3,000 before deciding between pagination and
virtualisation.

**3.4 Roughly 3.5 MB of duplicated, never-cached inline script.**
Measured inline bytes:

| page | inline JS | inline CSS |
|---|---:|---:|
| `map.html` | 60 KB | 34 KB |
| `index.html` | 44 KB | 20 KB |
| `updates.html` | 11 KB | 8 KB |
| `achievements.html` | 11 KB | 7 KB |
| `archive.html` | 9 KB | 8 KB |
| each of 712 legend pages | ~5 KB | — |

HTML is served `max-age=0, must-revalidate`, so all of this re-downloads on every navigation and
is never shared between pages. The 712 legend pages alone carry about 3.5 MB of identical
script. This is the same debt that keeps `'unsafe-inline'` in the CSP — extracting the shared
code to real modules fixes the caching problem and unblocks the CSP hardening in one move.

### S4 — Maintainability

**4.1 `.git` is 799 MB for a static site.** Large ornament PNG masters (2 MB+ each) were
committed before `assets/ornaments/generated-variants/*.png` was added to `.gitignore`. Every
clone still pays for them. Worth a history rewrite, but only as a deliberate standalone
operation with a backup — not folded into a feature branch.

**4.2 Two tracked scratch files:** `batch12.txt` and `ctx12.txt`. These are exactly the case the
repo-hygiene rule exists for. Confirm before untracking.

**4.3 `achievements.html` is the one page not following the site's escaping discipline.**
Line 291 renders `section.title`, `a.name`, `a.description`, `a.req` and `a.id` straight into
`innerHTML` via template literals. The data comes from first-party
`assets/achievements/achievements.json`, so this is not exploitable — but everywhere else the
codebase is disciplined (`map.html` has a proper `escapeHtml()` and `safeSourceUrl()`,
`buildSidebarList()` uses `textContent`, `generate_pages.py` routes through an `esc()` helper).
Fold this into the shared-DOM-utility work rather than treating it as a vulnerability.

### What the code review found to be already correct

Worth recording so this work is not repeated:

- **Turnstile is verified server-side.** `submit-bug`, `submit-feedback` and `submit-legend` all
  POST to `challenges.cloudflare.com/turnstile/v0/siteverify` and return 403 on failure. The
  literal red-team action "audit server-side Turnstile validation" is satisfied — but the
  *client-side widget lifecycle* is not (see S2.4), and `submit-feedback` verifies Turnstile
  correctly and then fails to write the row at all (see S1.3). Server-side validation and when the challenge
  runs are separate questions, and only the first one was clean.
- **Telemetry already sends `location.pathname`, not `location.href`** — in `index.html:1187`,
  `about.html:269`, `updates.html:455`, `legend-page.js:17` and the generated-page snippet in
  `generate_pages.py:811`. No change needed.
- **Private tables already fail anonymous read.** `analytics_events`, `bug_reports`, `feedback`
  and `legend_submissions` have RLS on, zero policies, and zero anon grants. That Phase-3 success
  criterion is already met; the RLS test suite should lock it in, not create it.
- **No secrets have ever been committed.** `git log --all` over `gsc-token.json`,
  `gsc-oauth-client.json`, `gsc-service-account.json` and `.env` returns nothing.
- **`legends` has no private columns today.** All 21 columns are public-facing. The
  `public_legends` view is future-proofing against a column added later, not a live leak.
- **`submit-legend` validates URL scheme** (`http:`/`https:` only) and all four functions screen
  free text against injection patterns and quarantine rather than silently accepting.

### Where the reviews appear to be mistaken

- **"Complete or remove visibly incomplete period filtering."** There is no incomplete period
  filter on the map. `period` appears in `map.html` only at line 1599/1612, where it contributes
  to *search scoring*. Period browsing is a separate surface at `/legends/period/*` and works.
  Before spending time here, establish what was actually seen.
- **"Remove 'team' and plural 'editors' language."** A grep across the hand-written pages finds
  no instance. If it exists it is on a generated page; find the source string in
  `generate_pages.py` rather than editing output.
- **"Apply a sensible query limit rather than relying on 10,000 records."** The `limit=10000` in
  `map.html:1883` is a ceiling, not a fetch size — 709 rows are returned. Worth lowering as
  hygiene, but it is not the cause of any current slowness. `?v=Date.now()` (3.1) is.

---

## Part 2 — The roadmap

Seven stages. Stages 1 and 2 are sequenced; after that, the content workstream runs continuously
alongside whatever engineering stage is active.

### Stage 1 — Trust and truth (week 1) — COMPLETE (2026-08-21)

| item | commit |
|---|---|
| 1.0 `GRANT INSERT` on `feedback` to `service_role` | `6caf30e8` |
| 1.1 `geolocation=(self)` | `7f7e393a` |
| 1.2 Privacy Notice rewrite + retention implemented | `388cdc56` |
| 1.3 least privilege on `legends` | `c6f9dc61` |
| 1.4 edge-function type guards | `edf1b16d` |
| 1.5 domain email addresses | `c6f9dc61` |
| 1.6 "first live pass" removed | `c6f9dc61` |
| 1.7 CSP `connect-src` pinned + `form-action` | `84c21f4a` |
| 1.8 Turnstile explicit render | `35260c2a` |

Carried into Stage 2: the **analytics grant** (1.0a/1.0b), deliberately held back so it ships
with `submit-event`'s rate limiting and field validation rather than briefly exposing a working
but unprotected public write endpoint. `analytics_events` therefore remains empty by design.

Two items below were found to be wrong during the work and are corrected in place: the
suspected CSP block on Cloudflare Web Analytics (it was working), and the scope of the
`?.trim()` crash (three functions, not one).

#### Original plan

Everything here is either factually wrong on a live page or a one-line security fix.

| # | Action | Source | Effort |
|---|---|---|---:|
| 1.0 | **`GRANT INSERT` to `service_role` on `analytics_events` and `feedback`** — both silently dead in prod | Code review S1.3 | 15 min |
| 1.0a | Add `home_cta_click` to the function allowlist **and** the table CHECK constraint | Code review S2.2a | 15 min |
| 1.0b | Make `submit-event` return the real status; add volume alerting so the next outage is visible | Code review S1.3 | 1 hr |
| 1.1 | `Permissions-Policy: geolocation=(self)` in `_headers` | Code review S1.1 | 5 min |
| 1.2 | Rewrite the Privacy Notice against actual collection | Code review S1.2 + red team | Half day |
| 1.3 | `REVOKE ALL` on `legends`, re-`GRANT SELECT` to `anon` | Code review S2.1 | 15 min |
| 1.4 | Fix `submit-legend` `sanitise()` type guard | Code review S2.3 | 10 min |
| 1.5 | Replace `folkloremap.conjoined774@passinbox.com` (4 pages) with domain addresses | All three reviews | 1 hr |
| 1.6 | Remove "This is a first live pass" from `achievements.html:120` | Marketing | 5 min |
| 1.7 | Pin CSP `connect-src` to `https://canjzkpvjwvkbjcduaaj.supabase.co`; add `form-action 'self'` | Red team | 15 min |
| 1.8 | Turnstile to explicit render, fired on modal open (`map.html`, `updates.html`) | Code review S2.4 | 1 hr |

**Verify 1.1 properly.** Deploy, then load the homepage and click the button — the fix is only
real when a browser permission prompt actually appears. Curl confirms the header, not the API.

**Privacy Notice acceptance criteria.** The rewrite must cover: the optional feedback email and
its retention; feedback message content and retention; first-party usage events sent to Supabase
and what fields they carry; the pseudonymous `session_id` and its lifetime; Supabase and
Cloudflare as processors for each purpose; rights and a working contact route; browser-local
Archive/seal/collection data; and the fact that geolocation coordinates never leave the browser.
Delete the "we do not ask for your name or email anywhere" sentence. Set an explicit retention
period for `analytics_events` and implement it as a scheduled delete, so the notice describes
something that is actually true.

**Email addresses.** `hello@`, `corrections@`, `submissions@` at `folklorefinder.uk`. The
current address reads as disposable, which undercuts a site whose entire pitch is editorial
credibility.

### Stage 2 — Endpoint and data-layer hardening (weeks 1–2)

**Prerequisite: Stage 1.0 must have shipped.** Hardening an endpoint that cannot write is
wasted work, and the grant fix and the rate limiting should land together so the pipeline is
never briefly working-but-unprotected.

**2.1 Harden `submit-event`.** Per-event-type field allowlisting (reject fields that do not
belong to the declared type), a request body size cap, rate limiting and burst deduplication
keyed on `session_id` plus IP, explicit short retention with a scheduled delete, and an alert on
abnormal write volume. Keep CORS exact-origin, but do not treat it as authentication — it is
trivially bypassed outside a browser.

**2.2 Create the `public_legends` view.** Published records only, exposing only the fields the
site reads. Point `map.html`, `nav-search.js` and any other reader at it. Framed correctly: this
is so that a private column added in six months is not public by default. It is not fixing a
current leak.

**2.3 Automated RLS regression tests.** A script that authenticates as `anon` and asserts:
readable published legends; zero rows from `bug_reports`, `feedback`, `legend_submissions`,
`analytics_events`; UPDATE and DELETE on legends both fail; a newly-added private column is not
returned by `public_legends`. Run it quarterly and after any migration. Most of these already
pass — the point is to keep them passing.

**2.4 Migrate to the publishable-key format** from the legacy anon JWT in `map.html:1812`.

**2.6 Submission-review workflow.** Treat every submitted string as hostile. Display URLs as
plain text with the hostname broken out and punycode revealed; flag shorteners; never auto-fetch
or unfurl a submitted URL; open links in a separate low-privilege browser profile, never the one
holding Cloudflare, GitHub or Supabase sessions. If a backend ever fetches submitted URLs, SSRF
controls go in first.

### Stage 3 — Performance and structure (weeks 2–4)

**3.1 Kill the cache-busters** (S3.1). Replace both `Date.now()` calls with the manual `?v=`
convention already used for CSS. Note the trap recorded in `project_current_state`: assets are
served immutable for a year, so a version bump that does not actually change ships nothing.

**3.2 Scope the bookmark update** (S3.2). Update only the toggled marker's popup.

**3.3 Paginate or virtualise the entries panel** (S3.3). Decide with evidence: generate 1,500
and 3,000 synthetic legends and measure filter-change time before choosing an approach. Keep the
local JSON fallback. Give the loading and failure states real branding — `onDataError` currently
inserts a raw `⚠` and tells the visitor to check the browser console.

**3.4 Extract shared modules** (S3.4). Target order, highest duplication first: analytics, the
session-id snippet, nav search, share cards, archive/progress storage, achievements, forms and
Turnstile, Supabase access, map and marker management, DOM rendering. Not a framework migration
— the goal is that each concern is testable on its own and cached once across 712 pages.

**3.5 Remove `'unsafe-inline'` from `script-src`.** This is the payoff for 3.4 and should follow
it directly. Replace inline `onclick` handlers (10 in `map.html`, 7 in `updates.html`) with
listeners, move remaining inline scripts to external modules, add nonces or hashes during the
migration, and turn on CSP report-only monitoring before enforcing.

**3.6 Shared safe-DOM utilities.** One `escapeHtml`, one `safeUrl`, one external-link builder,
one card renderer, one popup builder. `map.html` already has good versions of the first two —
promote them rather than writing new ones. Fold in `achievements.html:291` (S4.3).

**3.7 Asset delivery.** Responsive sizes on collection and legend pages, lazy-load below the
fold, and continue the WebP conversion. Use Pillow only, per the constraint recorded in
`project_image_delivery`.

**3.8 Repo hygiene.** Untrack `batch12.txt` and `ctx12.txt` after confirming. Schedule the 799 MB
history rewrite as its own operation with a full backup first.

### Stage 4 — Brand system (weeks 3–4)

Cheap changes with a high effect on how deliberate the product feels.

**Vocabulary.** One name per thing, everywhere: **Map**, **My Archive**, **Collections**,
**Explorer Seals**, **Research Journal**. "Collections" is the product label; "themed trails" is
descriptive copy only, never an interface name.

**Iconography.** Replace emoji category symbols with custom SVG glyphs in a single woodcut or
engraved style. `map.html` already stores category art as `iconPath` SVG path data, so the
plumbing exists — this is an art task, not an engineering one.

**System documentation.** Palette, typography, spacing, buttons, cards, labels, borders,
botanical dividers. Dusk and parchment must read as two expressions of one system.

**Creator identity.** A short first-person founder note on why Folklore Finder exists, with no
private details. Resolve EditionTree to either "An EditionTree project" with a one-line
explanation, or a discreet publisher credit that does not compete with the product name.

**Artwork direction.** Keep the AI labelling as-is. Gradually mix in place photography, historic
maps, archival illustration, public-domain engravings and source-document excerpts. This
supports the "rooted in real places and research" claim and reduces the risk of dismissal as an
AI-art site.

Run every fresh sentence written in this stage through `no-ai-slop`.

### Stage 5 — Activation and retention (month 2)

**Homepage hierarchy**, once 1.1 has actually shipped and been verified in a browser: Find
folklore near me → Explore the map → Surprise me, with search prominent throughout.

**Delay the "Know a legend we've missed?" prompt** until the visitor has opened several legends,
reached the end of an entry, visited About, or partly completed a collection. Do not ask for a
contribution before demonstrating value.

**My Archive** stays accountless and local-first — that is a genuine differentiator, not a gap.
Add export, import, a downloadable Explorer's Record, a print-friendly saved list, and clear
recovery guidance.

**Explorer Seals.** Rename consistently. Replace the wall of `???` with silhouettes or partial
clues, surface the three nearest seals, explain how progress is earned, generate a branded share
card on unlock, and keep a handful genuinely secret.

**Collections.** Show the next undiscovered entry, add a map view and estimated geographic
scope, make them shareable, offer a printable companion guide, and change "Begin Collection" to
"Explore Collection" for first-time visitors.

### Stage 6 — Marketing engine (from month 2, ongoing)

**Positioning.** *A living, researched atlas of folklore across Britain and Ireland — pinning
every story to its place and letting you build a personal archive as you explore.* Keep "Every
place has a story." Add "Researched, not repeated" as the trust line.

**Three share formats**, in build order: the local discovery card ("12 legends within 20 miles
of Lancaster", with a small map and one featured legend), the Explorer Seal card, and the
collection card. These travel; "visit my website" does not.

**The Folklore Dispatch.** One optional monthly email: a featured legend, a place or regional
trail, recent additions, one research note, one collection or download. Monthly is enough — the
constraint is sustainability, not reach.

**Surface the Research Journal on-site.** `updates.html` currently shows Ko-fi buttons where it
should show journal previews. Ko-fi stays the support and download destination; the site does
the discovery.

### Stage 7 — Regional pilot (month 3)

One region, run end to end as a repeatable template. Pick on evidence — strongest combination of
entry count, artwork and credible sourcing — rather than defaulting to Lancashire for
familiarity, though local knowledge is a real tiebreaker.

Sequence: audit and improve the region's ten most compelling legends → build a regional landing
page or collection → produce a small free field guide → make three local-discovery graphics →
approach local history societies, folklore groups, libraries, museums, walking organisations,
local media and heritage bodies. Frame outreach as a request for corrections and an invitation
to contribute, plus a free resource for their audience. Measure referrals, second-page visits,
saves and collection starts. Refine before repeating.

---

## Continuous workstreams

### Content and sourcing

Carried over from Cycle 2 and running throughout.

- **Finish the zero-em-dash cleanup.** A scoped pass missed 1,937 instances; this is the
  standing Cycle 2 priority.
- **Enhancement must expand, not just polish.** Cycle 1 left the dataset net shorter despite
  finding more sources. Cycle 2's job is source-synthesis expansion.
- **Prioritised sourcing audit**, in this order: homepage-featured legends → highest
  search-traffic entries → famous legends likely to attract scrutiny → entries used in
  campaigns → Wikipedia-only entries → AI-generated entries with weak sourcing. Each flagship
  page should visibly demonstrate the editorial promise through primary, heritage or scholarly
  material.
- **Editorial checklist per published legend:** accurate title and location; folklore-versus-
  history distinction; source classification; dating confidence; AI-art disclosure; related and
  nearby legends; collection links; safe source links; correct social metadata; a clear
  continuation route.

### Operational security

Not assessable from the code, so it needs deliberate confirmation:

MFA on GitHub, Cloudflare and Supabase · separate admin and everyday browser profiles · branch
protection on `main` · secret scanning · dependency alerts · least-privilege database roles · no
shared service-role credentials · Supabase and Cloudflare budget alerts · Edge Function volume
alerts · tested backups · quarterly RLS regression run (Stage 2.3) · a documented incident and
rollback process.

---

## Definition of done

**Security** — `analytics_events` and `feedback` actually receive rows, verified by probe;
private tables fail every anonymous-read test; public data comes from
`public_legends`; `anon` holds `SELECT` and nothing else on `legends`; `submit-event` is
validated and rate-limited; the Privacy Notice matches what is actually collected; no public
contact surface looks disposable.

**Performance** — the map stays responsive at twice the current dataset; the entries panel is
paginated or virtualised; `legends.json` and `legend_pages.json` are genuinely cacheable; shared
JS is extracted and `'unsafe-inline'` is gone from `script-src`; mobile navigation is reliable;
no high-impact accessibility failures.

**Brand** — vocabulary and iconography are consistent; the creator voice is human; flagship
entries visibly support the sourcing promise; Explorer Seals no longer read as unfinished; the
homepage has an obvious action hierarchy.

**Marketing** — local, seal and collection share cards exist; one owned return channel is live;
one regional campaign is complete; five or more credible organisations have been approached;
referral and onward-exploration behaviour is measurable.

## Deferred until the above is substantially complete

Name generator · user accounts · merchandise ranges · new gamification systems · framework
migration · international expansion · chasing raw entry count · paid advertising · daily social
posting · subscription tiers.

The value in this phase is making the existing 709 entries safer, faster, more trustworthy and
easier to spread. That is worth more than reaching 1,000.
