import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? ''
const SUPABASE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

// No CORS allowlist and no Origin check here, unlike the other functions.
// Violation reports are sent by the browser itself, not by page script: they
// carry no Origin the way a fetch does, and they are not subject to CORS. The
// filtering and limits below are what stands in for that.
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

const MAX_BODY_BYTES = 8192

// Extensions are the overwhelming majority of CSP reports on any public site,
// and none of them indicate a problem with this one. A user with an ad blocker
// or a password manager generates violations continuously. Dropping these
// before they reach the database is the difference between a signal and a
// firehose.
const IGNORED_SCHEMES = [
  'chrome-extension:', 'moz-extension:', 'safari-extension:',
  'safari-web-extension:', 'webkit-masked-url:', 'chrome:', 'resource:',
  'about:',
]

// Values the browser substitutes when it will not disclose the real one. They
// carry no information and would otherwise each become their own fingerprint.
const OPAQUE = ['inline', 'eval', 'data', 'blob', '']

const RATE_WINDOW_MS = 60_000
const MAX_PER_IP_PER_WINDOW = 30
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

function clean(v: unknown, max: number): string {
  return text(v).trim().slice(0, max).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
}

// document-uri and referrer are full URLs and may carry query strings. Only the
// path is kept, so a violation report never becomes a record of what someone
// searched for. Matches how referring_page is handled in submit-event.
function pathOf(v: unknown): string {
  const raw = text(v)
  if (!raw) return ''
  try { return new URL(raw).pathname.slice(0, 300) } catch { return '' }
}

// Keep the scheme and host of a blocked URI but discard its path and query. The
// useful question is "what origin was blocked", and the rest is where a report
// could otherwise smuggle in something personal.
function originOf(v: unknown): string {
  const raw = clean(v, 500)
  if (!raw) return ''
  if (OPAQUE.includes(raw)) return raw
  try { const u = new URL(raw); return `${u.protocol}//${u.host}` } catch { return raw.slice(0, 100) }
}

function ignorable(...values: string[]): boolean {
  return values.some(v => IGNORED_SCHEMES.some(s => v.startsWith(s)))
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })
  // Always 204 from here on. A browser has nothing useful to do with an error
  // from a reporting endpoint, and a talkative one only helps someone probing.
  const ok = () => new Response(null, { status: 204, headers: CORS })
  if (req.method !== 'POST') return ok()

  const ip = req.headers.get('CF-Connecting-IP') ?? req.headers.get('x-forwarded-for') ?? 'unknown'
  if (ipRateLimited(ip)) return ok()

  let raw: string
  try { raw = await req.text() } catch { return ok() }
  if (!raw || raw.length > MAX_BODY_BYTES) return ok()

  let parsed: unknown
  try { parsed = JSON.parse(raw) } catch { return ok() }

  // Two wire formats. report-uri sends {"csp-report": {...}} with hyphenated
  // keys; the newer Reporting API sends an array of {type, body:{...}} with
  // camelCase keys. Both are declared in _headers, so both must be understood.
  const items: Record<string, unknown>[] = []
  if (Array.isArray(parsed)) {
    for (const entry of parsed) {
      const e = entry as Record<string, unknown>
      if (e && e.type === 'csp-violation' && e.body) items.push(e.body as Record<string, unknown>)
    }
  } else if (parsed && typeof parsed === 'object') {
    const p = parsed as Record<string, unknown>
    if (p['csp-report']) items.push(p['csp-report'] as Record<string, unknown>)
  }
  if (!items.length) return ok()

  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)

  for (const r of items.slice(0, 10)) {
    const directive = clean(r['effective-directive'] ?? r.effectiveDirective ??
                            r['violated-directive'] ?? r.violatedDirective, 100)
    const blocked   = originOf(r['blocked-uri'] ?? r.blockedURL)
    const source    = originOf(r['source-file'] ?? r.sourceFile)
    const docPath   = pathOf(r['document-uri'] ?? r.documentURL)
    const line      = Number(r['line-number'] ?? r.lineNumber) || null

    if (!directive) continue
    if (ignorable(blocked, source)) continue

    // Fingerprint excludes the line number: the same violation shifting by a
    // line after an edit is the same violation, and including it would split
    // one problem into many rows.
    const fingerprint = [docPath, directive, blocked, source].join('|').slice(0, 500)

    const { error } = await supabase.rpc('record_csp_violation', {
      p_fingerprint: fingerprint,
      p_document_path: docPath || null,
      p_effective_directive: directive,
      p_blocked_uri: blocked || null,
      p_source_file: source || null,
      p_line_number: line,
    })
    if (error) console.error('CSP_REPORT_INSERT_FAILED', error)
  }

  return ok()
})
