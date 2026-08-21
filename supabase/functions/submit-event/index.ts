import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? ''
const SUPABASE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

// Allowed browser origins for CORS. folklorefinder.uk is the live site; the old
// *.pages.dev URL bounces to it client-side. Reflect the request origin only
// when it's on the allowlist. CORS is not an authentication control here — a
// plain curl reaches this function, which is why the limits below exist.
const ALLOWED_ORIGINS = [
  'https://folklorefinder.uk',
  'https://www.folklorefinder.uk',
]

function cors(req: Request): Record<string, string> {
  const origin = req.headers.get('Origin') ?? ''
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0]
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Vary': 'Origin',
  }
}

// Which fields each event type may carry. Previously any allowlisted event
// could set any column, so an achievement_unlocked was free to arrive with a
// period_slug. Anything not listed for the declared type is dropped rather
// than rejected: a stale cached page sending an extra field should still have
// its event counted, it just should not be able to write junk into a column.
const EVENT_FIELDS: Record<string, readonly string[]> = {
  legend_viewed:            ['legend_name'],
  collection_viewed:        ['collection_slug'],
  period_viewed:            ['period_slug'],
  guide_viewed:             ['guide_id'],
  guide_downloaded:         ['guide_id'],
  kofi_link_clicked:        ['item_id'],
  research_journal_clicked: ['item_id'],
  achievement_unlocked:     ['item_id'],
  achievement_progress:     ['item_id'],
  feedback_submitted:       ['item_id'],
  product_clicked:          ['item_id'],
  home_cta_click:           ['item_id'],
}

const COLUMNS = [
  'legend_name', 'collection_slug', 'period_slug', 'guide_id', 'item_id',
] as const

// A single event is a few hundred bytes. Anything approaching this is either
// broken or hostile, and req.json() would otherwise buffer whatever arrives.
const MAX_BODY_BYTES = 2048

// Best-effort per-IP limiting, held in isolate memory and never written down.
// The Privacy Notice states we do not store your IP address, so this must stay
// ephemeral: no database column, no log line. Isolates recycle and several may
// run at once, so this is a speed bump on floods rather than a hard guarantee.
// The per-session database limit below is the durable half.
const RATE_WINDOW_MS = 60_000
const MAX_PER_IP_PER_WINDOW = 120
const MAX_PER_SESSION_PER_WINDOW = 60
const ipHits = new Map<string, { n: number; resetAt: number }>()

function ipRateLimited(ip: string): boolean {
  const now = Date.now()
  if (ipHits.size > 5000) {
    for (const [k, v] of ipHits) if (now > v.resetAt) ipHits.delete(k)
  }
  const entry = ipHits.get(ip)
  if (!entry || now > entry.resetAt) {
    ipHits.set(ip, { n: 1, resetAt: now + RATE_WINDOW_MS })
    return false
  }
  entry.n += 1
  return entry.n > MAX_PER_IP_PER_WINDOW
}

function text(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function sanitise(v: unknown, max: number): string {
  return text(v).trim().slice(0, max).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
}

// referring_page is a path, never a URL. Every caller sends location.pathname.
// Rejecting anything else stops this column being used to store arbitrary
// absolute URLs, and keeps it consistent with what the Privacy Notice says we
// record ("the path of the page you were on", not the full web address).
function safePath(v: unknown): string | null {
  const p = sanitise(v, 500)
  if (!p.startsWith('/') || p.includes('://') || p.startsWith('//')) return null
  return p
}

function json(body: unknown, status: number, CORS: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status, headers: { ...CORS, 'Content-Type': 'application/json' },
  })
}

Deno.serve(async (req: Request) => {
  const CORS = cors(req)

  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })
  if (req.method !== 'POST') return json({ error: 'Method not allowed' }, 405, CORS)

  const ip = req.headers.get('CF-Connecting-IP') ?? req.headers.get('x-forwarded-for') ?? 'unknown'
  if (ipRateLimited(ip)) return json({ error: 'Too many requests' }, 429, CORS)

  const declared = Number(req.headers.get('Content-Length') ?? '0')
  if (declared > MAX_BODY_BYTES) return json({ error: 'Payload too large' }, 413, CORS)

  // Read as text first so an oversized body is capped before it is parsed.
  let raw: string
  try { raw = await req.text() } catch { return json({ error: 'Invalid request' }, 400, CORS) }
  if (raw.length > MAX_BODY_BYTES) return json({ error: 'Payload too large' }, 413, CORS)

  let body: Record<string, unknown>
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error()
    body = parsed as Record<string, unknown>
  } catch { return json({ error: 'Invalid request' }, 400, CORS) }

  const event_type = text(body.event_type)
  const allowedFields = EVENT_FIELDS[event_type]
  if (!allowedFields) return json({ error: 'A valid event_type is required' }, 400, CORS)

  // Build the row from the permitted fields only. Everything else in the body,
  // nested objects included, is ignored and never reaches the database.
  const row: Record<string, string | null> = {
    event_type,
    referring_page: safePath(body.referring_page),
    session_id: body.session_id ? sanitise(body.session_id, 100) || null : null,
  }
  for (const col of COLUMNS) {
    row[col] = allowedFields.includes(col) && body[col]
      ? (sanitise(body[col], 200) || null)
      : null
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)

  // Per-session limiting. Durable, unlike the per-IP counter, and it does not
  // require storing anything we have said we do not store.
  if (row.session_id) {
    const since = new Date(Date.now() - RATE_WINDOW_MS).toISOString()
    const { count, error: countErr } = await supabase
      .from('analytics_events')
      .select('*', { count: 'exact', head: true })
      .eq('session_id', row.session_id)
      .gte('created_at', since)
    if (countErr) {
      console.error('ANALYTICS_RATE_CHECK_FAILED', countErr)
    } else if ((count ?? 0) >= MAX_PER_SESSION_PER_WINDOW) {
      return json({ error: 'Too many requests' }, 429, CORS)
    }

    // Burst deduplication: the same event, from the same session, within the
    // same minute, collapses to one row via the unique index on dedup_key.
    const bucket = Math.floor(Date.now() / 60_000)
    row.dedup_key = [
      row.session_id, event_type, row.legend_name ?? '', row.collection_slug ?? '',
      row.period_slug ?? '', row.guide_id ?? '', row.item_id ?? '', bucket,
    ].join('|')
  }

  const { error: dbErr } = await supabase
    .from('analytics_events')
    .upsert(row, { onConflict: 'dedup_key', ignoreDuplicates: true })

  if (dbErr) {
    // Report the real status. The previous version returned 200 {success:true}
    // whatever happened, which is why a six-week total outage produced no
    // signal at all. The client ignores the response either way, so an honest
    // status costs nothing and makes the failure visible. The distinctive
    // prefix is here to be alerted on.
    console.error('ANALYTICS_INSERT_FAILED', dbErr)
    return json({ error: 'Event not recorded' }, 500, CORS)
  }

  return json({ success: true }, 200, CORS)
})
