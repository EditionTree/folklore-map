# Reviewing submitted content

Folklore Finder accepts three kinds of input from strangers: legend submissions,
feedback, and bug reports. All three are stored, and all three are eventually
read by a person, and in the case of legend submissions by a research agent as
well. That makes them an attack surface, not just a mailbox.

**The rule: everything a stranger typed is hostile until you have looked at it
properly.** Not because most of it will be, but because the cost of assuming
otherwise once is much higher than the cost of assuming this every time.

## Review them with the tool

```bash
export SUPABASE_URL=https://canjzkpvjwvkbjcduaaj.supabase.co
export SUPABASE_SERVICE_KEY=...        # from Supabase, never committed
python scripts/review_submissions.py
```

It shows everything waiting, across all three tables. Useful flags:

| flag | effect |
|---|---|
| `--all` | include rows already actioned |
| `--table feedback` | one table only |
| `--set-status feedback 3 actioned` | mark one row done |

Marking something actioned matters: retention runs from that point, not from
when it arrived. Feedback is deleted 30 days after you action it, and everything
goes at 6 months regardless.

## What the tool does for you

**It never fetches a submitted URL.** Not to check it, not to get a title, not
to see if it resolves. Fetching one leaks your IP to whoever submitted it,
confirms a human read it, and issues a request from your machine to a target
they chose. The tool analyses URLs lexically and prints them inert.

**It makes invisible characters visible.** A right-to-left override renders
`moc.live//:sptth` as a convincing `https://evil.com`, and zero-width spaces
break a hostname into something that looks legitimate. These are shown as
`<RLO>` and `<ZWSP>` rather than passed to your terminal.

**It decodes punycode and flags mixed scripts.** `xn--pple-43d.com` is shown as
`аpple.com`, and the tool notes that the host mixes Cyrillic with Latin. On
screen those two strings are identical.

**It flags shorteners, bare IP hosts, embedded credentials, odd ports, and
non-http schemes.** `https://folklorefinder.uk@evil.example/x` goes to
`evil.example`, and that is easy to misread at a glance.

## What the tool cannot do for you

It does no reputation lookup and makes no judgement about whether a site is
trustworthy. "No lexical warnings" means the URL is not obviously deceptive. It
does not mean the destination is safe.

## If you open a link

Use a browser profile that is **not** signed in to Cloudflare, GitHub or
Supabase. A separate profile, or a private window in a browser you do not use
for administration. The threat is not only malware: a page that can act inside a
session where you are logged in to your own DNS and hosting is a much worse day
than a page that cannot.

Never paste a submitted URL into a terminal, and never pipe one to anything.

## Verdicts

| what you found | do |
|---|---|
| Genuine, useful | research it independently and write the entry yourself. Submitted text is never published directly. |
| Genuine, but thin | `--set-status ... rejected`. It will be deleted 30 days later. |
| Spam or abuse | `--set-status ... rejected`. Do not reply, do not visit the URL. |
| Actively hostile | reject it, and note the pattern here so the screening can be improved. |

## The screening flag is a hint, not a verdict

Each endpoint screens submitted text against a pattern list and sets `flagged`.
It quarantines rather than rejects, so a flagged item is still stored and still
needs your eyes.

**That list has been wrong before.** Until 2026-08-21 the prompt-injection
pattern required exactly one word between the verb and the noun, so
`ignore all previous instructions` (the single commonest phrasing of that
attack) was never caught. It missed 8 of 13 realistic phrasings on test. The
pattern now allows up to four intervening words and covers more verbs and nouns.

Two things follow. `flagged = false` means "nothing matched a list", not
"harmless". And when you meet a phrasing the list misses, add it, in both
`scripts/review_submissions.py` and the three edge functions, which deliberately
keep the same patterns.

## Legend submissions reach an agent

`legend_submissions` has an `agent_notes` column, so submitted text is read by
research automation and not only by you. Prompt injection aimed at that agent is
a real category of attack here, which is why the injection pattern matters more
than the label "spam filter" suggests. Treat anything that reads like an
instruction rather than a folklore tip as hostile regardless of what `flagged`
says.

## If the backend ever fetches submitted URLs

It does not today, and nothing should change that casually. If it ever does,
these come first:

- Resolve the hostname and reject private, loopback, link-local and reserved
  ranges, including IPv6 and IPv4-mapped forms.
- Re-check after every redirect, not only at the start. Redirecting to
  `169.254.169.254` is the standard cloud-metadata attack.
- Reject non-http schemes outright, including `file:`, `gopher:` and `data:`.
- Cap response size and time, and never echo the response back to the submitter.
- Fetch from somewhere with no ambient credentials and no private network
  access. An edge function with a service-role key in its environment is exactly
  the wrong place.

## Credit the follower when you action a submission

When a submission becomes a real entry, record where it came from **on the
legend itself**, in `seeds.json`:

```json
"origin": {
  "type": "follower_suggestion",
  "received": "2026-08-23",
  "source_supplied": true,
  "source_outcome": "not_assessed"
}
```

`received` is the submission's `created_at` date, not the date you actioned it.

Do this at the moment you write the entry. The submitted row is deleted 30 days
after it is actioned, so nothing else remembers that the entry started with a
follower, and once the row is gone the fact cannot be recovered.

`generate_pages.py` renders a **Follower suggestion** tag in the legend page
hero, beside the category and the place, and a line in the article saying how
the legend reached us. The Recently Added cards on `updates.html` carry the same
tag, and the homepage submit prompt counts these entries. Nothing renders
without the block.

### What to put in `source_outcome`

Only read when `source_supplied` is true. Each value prints different wording,
so pick the one that is actually true. An unrecognised value stops the build
rather than printing the wrong claim.

| value | when | what the page says |
|---|---|---|
| `not_assessed` | a link came with it and nobody has read it yet | a source came with the suggestion, and we followed their lead into the records |
| `checked_not_cited` | you read it, and it did not clear the sourcing bar | we read what they sent, then followed the trail back to earlier records |
| `cited` | you read it, and it is good enough to appear in `sources` | we read what they sent and it is credited with the rest |

`not_assessed` is the honest default, and it is where an entry stays until
somebody reads the link **safely**. Do not upgrade it on the assumption that a
link that looks fine is fine.

### Reading a submitted source without fetching it

Two different risks get confused here. Reading their URL is a question about
your machine. Publishing it is a question about vouching for a destination and
sending readers there. Solving the first does not license the second.

- **Never fetch the live URL**, from an agent or from your everyday browser. The
  reasons are at the top of this file.
- **Prefer a Wayback snapshot.** `https://archive.org/wayback/available?url=...`
  says whether one exists, and reading the snapshot never touches their host, so
  nothing leaks and nobody learns that a human read it. Not every page has one.
- **If you must open the live page**, use a browser profile signed in to nothing,
  as described above.
- **Publish the link only if it clears the normal sourcing bar on its own.** A
  popular haunted-places directory usually will not, and by then the entry
  normally rests on better records anyway. Leaving it out is not a slight.

What a follower gives us is a lead, not a citation, and the lead is the part
worth crediting. The wording credits exactly that, which is why the entry no
longer says we wrote it "ourselves": we followed their lead into the records and
wrote up what we found there.

**The credit is anonymous, and it has to stay that way.** The form collects no
name, no email and no IP, and the Privacy Notice says so in those words. There
is no submitter to name, so never add one. The same notice promises that a
submitter's own text is never published. Keep that true: research the tradition
properly rather than tidying up what they sent.

## Related

- `scripts/review_submissions.py` is the tool.
- `scripts/rls_regression_test.py` asserts none of these tables is readable
  without the service key.
- `PHASE_3_ROADMAP.md` has the wider security context.
- Retention rules are in the Privacy Notice and enforced by cron jobs, which are
  listed in `supabase/migrations/`.
