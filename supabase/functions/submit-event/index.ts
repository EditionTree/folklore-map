import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? ''
const SUPABASE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

// Allowed browser origins for CORS. folklorefinder.uk is the live site; the old
// *.pages.dev URL bounces to it client-side. Reflect the request origin only
// when it's on the allowlist.
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

const EVENT_TYPES = [
  'legend_viewed',
  'collection_viewed',
  'period_viewed',
  'guide_viewed',
  'guide_downloaded',
  'kofi_link_clicked',
  'research_journal_clicked',
  'achievement_unlocked',
  'achievement_progress',
  'feedback_submitted',
  'product_clicked',
]

function sanitise(s: string, max: number): string {
  return String(s ?? '').trim().slice(0, max).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
}

Deno.serve(async (req: Request) => {
  const CORS = cors(req)

  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS })
  }
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  let body: Record<string, string>
  try { body = await req.json() } catch {
    return new Response(JSON.stringify({ error: 'Invalid request' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  const {
    event_type, legend_name, collection_slug, period_slug, guide_id, item_id,
    referring_page, session_id,
  } = body

  // ── Required fields ───────────────────────────────────────────────────
  if (!EVENT_TYPES.includes(event_type)) {
    return new Response(JSON.stringify({ error: 'A valid event_type is required' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  // ── Insert (service role — bypasses RLS; anon REST access is revoked) ──
  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)
  const { error: dbErr } = await supabase.from('analytics_events').insert({
    event_type,
    legend_name:       legend_name ? sanitise(legend_name, 200) : null,
    collection_slug:   collection_slug ? sanitise(collection_slug, 200) : null,
    period_slug:       period_slug ? sanitise(period_slug, 200) : null,
    guide_id:          guide_id ? sanitise(guide_id, 200) : null,
    item_id:           item_id ? sanitise(item_id, 200) : null,
    referring_page:    referring_page ? sanitise(referring_page, 500) : null,
    session_id:        session_id ? sanitise(session_id, 100) : null,
  })

  if (dbErr) {
    // Analytics failures shouldn't be noisy for users — log server-side and
    // still return 200 so the client doesn't retry or surface an error.
    console.error('DB insert error:', dbErr)
  }

  return new Response(JSON.stringify({ success: true }), {
    status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
  })
})
