import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const TURNSTILE_SECRET  = Deno.env.get('TURNSTILE_SECRET_KEY') ?? ''
const SUPABASE_URL      = Deno.env.get('SUPABASE_URL') ?? ''
const SUPABASE_KEY      = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

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

const FEEDBACK_TYPES = [
  'bug', 'missing_legend', 'incorrect_info',
  'feature_suggestion', 'source_suggestion', 'general',
]

// Injection / abuse patterns — screened against the free-text fields
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

  let body: Record<string, unknown>
  try { body = await req.json() } catch {
    return new Response(JSON.stringify({ error: 'Invalid request' }), {
      status: 400, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  const {
    feedback_type, message, page_url,
    related_legend, related_collection, contact_email,
    cf_turnstile_response,
  } = body

  // ── Required fields ───────────────────────────────────────────────────
  if (!text(message).trim() || !text(cf_turnstile_response).trim() ||
      !FEEDBACK_TYPES.includes(text(feedback_type))) {
    return new Response(JSON.stringify({ error: 'A message, a valid category and the security check are required' }), {
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

  // ── Sanitise inputs (match feedback table column limits) ───────────────
  const message_clean = sanitise(message, 2000)
  const page_url_clean = page_url ? sanitise(page_url, 500) : null
  const related_legend_clean = related_legend ? sanitise(related_legend, 200) : null
  const related_collection_clean = related_collection ? sanitise(related_collection, 200) : null
  const contact_email_clean = contact_email ? sanitise(contact_email, 320) : null

  // ── Injection / abuse screening (quarantine, do not reject) ───────────
  const allText = `${message_clean} ${contact_email_clean ?? ''}`
  const flagged = INJECTION.some(p => p.test(allText))

  // ── Insert (service role — bypasses RLS; anon REST access is revoked) ──
  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)
  const { error: dbErr } = await supabase.from('feedback').insert({
    feedback_type:       text(feedback_type),
    message:             message_clean,
    page_url:            page_url_clean,
    related_legend:      related_legend_clean,
    related_collection:  related_collection_clean,
    contact_email:       contact_email_clean,
    status:              'new',
    flagged,
    flagged_reason: flagged ? 'Suspicious pattern detected' : null,
  })

  if (dbErr) {
    console.error('DB insert error:', dbErr)
    return new Response(JSON.stringify({ error: 'Feedback could not be saved, please try again' }), {
      status: 500, headers: { ...CORS, 'Content-Type': 'application/json' },
    })
  }

  return new Response(JSON.stringify({ success: true }), {
    status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
  })
})
