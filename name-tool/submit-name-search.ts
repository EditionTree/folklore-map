// ============================================================================
// submit-name-search — Supabase Edge Function (NOT YET DEPLOYED)
// Kept standalone during the prototype phase. When ready, move to
// supabase/functions/submit-name-search/index.ts and deploy.
//
// Modelled on submit-event (NOT submit-legend): high-frequency, low-value,
// fire-and-forget logging — no Turnstile, always returns 200 so the client
// never retries or surfaces an error. Service-role insert bypasses RLS; anon
// REST insert on name_searches is revoked.
// ============================================================================
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? ''
const SUPABASE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

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

function sanitise(s: string, max: number): string {
  return String(s ?? '').trim().slice(0, max).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
}

Deno.serve(async (req: Request) => {
  const CORS = cors(req)
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  let body: Record<string, unknown>
  try { body = await req.json() } catch {
    return new Response(JSON.stringify({ error: 'Invalid request' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  const query_raw = sanitise(String(body.query_raw ?? ''), 200)
  if (!query_raw) {
    return new Response(JSON.stringify({ error: 'query_raw required' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }
  const matched = body.matched === true
  const matched_slug = body.matched_slug ? sanitise(String(body.matched_slug), 200) : null
  const session_id = body.session_id ? sanitise(String(body.session_id), 100) : null

  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)

  // Resolve slug -> id (nullable). Kept simple; a lookup failure is non-fatal.
  let matched_name_id: number | null = null
  if (matched_slug) {
    const { data } = await supabase.from('names').select('id').eq('slug', matched_slug).maybeSingle()
    matched_name_id = data?.id ?? null
  }

  const { error } = await supabase.from('name_searches').insert({
    query_raw, matched, matched_name_id, session_id,
  })
  if (error) console.error('DB insert error:', error) // stay quiet to the client

  return new Response(JSON.stringify({ success: true }), {
    status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
  })
})
