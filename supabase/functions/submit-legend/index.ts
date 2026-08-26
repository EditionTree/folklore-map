import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const TURNSTILE_SECRET  = Deno.env.get('TURNSTILE_SECRET_KEY') ?? ''
const SUPABASE_URL      = Deno.env.get('SUPABASE_URL') ?? ''
const SUPABASE_KEY      = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

// Allowed browser origins for CORS. folklorefinder.uk is the live site; the old
// *.pages.dev URL bounces to it client-side so a submission never reaches here
// from that origin. Reflect the request origin when it's on the allowlist.
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

// Injection / abuse patterns — checked against all text fields combined
const INJECTION = [
  // Matches "ignore all previous instructions" and its variants. The original
  // pattern allowed exactly one word between the verb and the noun, so the
  // commonest phrasing of this attack was not caught at all.
  /\b(?:ignore|forget|disregard|override|bypass)\s+(?:(?:the|all|any|your|these|those|of|previous|prior|above|earlier|preceding|system)\s+){0,4}(?:instructions?|rules?|commands?|prompts?|directives?|guidelines?)/i,
  /\b(DROP\s+TABLE|DELETE\s+FROM|TRUNCATE|INSERT\s+INTO|UPDATE\s+\w+\s+SET|ALTER\s+TABLE)/i,
  /<script/i,
  /javascript:/i,
  /eval\s*\(/i,
  /document\.write\s*\(/i,
  /on(load|click|error|mouseover)\s*=/i,
  /rm\s+-rf/i,
  /sudo\s+/i,
]

// JSON.parse yields arbitrary types, so a field the client declares as text can
// arrive as a number, an array or an object. `?.` guards null and undefined but
// not the wrong type — `(1)?.trim()` still throws — so narrow to string first.
function text(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function sanitise(v: unknown, max: number): string {
  return text(v).trim().slice(0, max).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
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

  // ── Parse body ────────────────────────────────────────────────────────
  let body: Record<string, unknown>
  try { body = await req.json() } catch {
    return new Response(JSON.stringify({ error: 'Invalid request' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  const { legend_name, region, description, source_url, cf_turnstile_response } = body

  // ── Required fields ───────────────────────────────────────────────────
  if (!text(legend_name).trim() || !text(region).trim() || !text(description).trim() ||
      !text(source_url).trim() || !text(cf_turnstile_response).trim()) {
    return new Response(JSON.stringify({ error: 'All fields are required' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  // ── Turnstile server-side verification ────────────────────────────────
  const form = new FormData()
  form.append('secret', TURNSTILE_SECRET)
  form.append('response', text(cf_turnstile_response))
  const cfRes  = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST', body: form,
  })
  const cfData = await cfRes.json()
  if (!cfData.success) {
    return new Response(JSON.stringify({ error: 'Verification failed, please try again' }), {
      status: 403, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  // ── Sanitise inputs ───────────────────────────────────────────────────
  const name_clean = sanitise(legend_name, 100)
  const region_clean = sanitise(region, 200)
  const desc_clean = sanitise(description, 500)
  const url_clean = sanitise(source_url, 500)

  // Validate source URL scheme (must be http/https)
  let validUrl = false
  try {
    const u = new URL(url_clean)
    validUrl = ['http:', 'https:'].includes(u.protocol)
  } catch { validUrl = false }
  if (!validUrl) {
    return new Response(JSON.stringify({ error: 'Source URL must be a valid http/https link' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  // ── Injection / abuse screening ───────────────────────────────────────
  const allText = `${name_clean} ${region_clean} ${desc_clean} ${url_clean}`
  const flagged = INJECTION.some(p => p.test(allText))

  // ── Insert ────────────────────────────────────────────────────────────
  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)
  const { error: dbErr } = await supabase.from('legend_submissions').insert({
    legend_name:    name_clean,
    region:         region_clean,
    description:    desc_clean,
    source_url:     url_clean,
    status:         flagged ? 'flagged' : 'pending',
    flagged,
    flagged_reason: flagged ? 'Suspicious pattern detected' : null,
  })

  if (dbErr) {
    console.error('DB insert error:', dbErr)
    return new Response(JSON.stringify({ error: 'Submission could not be saved, please try again' }), {
      status: 500, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  return new Response(JSON.stringify({ success: true }), {
    status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
  })
})
