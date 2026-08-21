-- Storage for Content-Security-Policy violation reports. Applied 2026-08-21.
--
-- Until this existed there was no way to tell a working CSP directive from one
-- silently blocking something. That gap is why the connect-src question during
-- Stage 1 had to be answered by reading vendor beacon source rather than by
-- evidence, and why a wrong conclusion was drawn from a 404 probe.
--
-- Rows are AGGREGATED, not appended. One misconfigured directive can generate
-- thousands of identical reports an hour; the signal is "this violation exists
-- and is happening N times", not N copies of it.
--
-- Deliberately stores no session id, no IP address and no user agent, and only
-- the path of the document rather than its full URL. A violation report is
-- operational data about the site, not about the visitor.
create table if not exists public.csp_reports (
  id                  bigint generated always as identity primary key,
  first_seen_at       timestamptz not null default now(),
  last_seen_at        timestamptz not null default now(),
  occurrences         integer     not null default 1,
  fingerprint         text        not null unique,
  document_path       text,
  effective_directive text,
  blocked_uri         text,
  source_file         text,
  line_number         integer,
  reviewed            boolean     not null default false
);

create index if not exists csp_reports_last_seen_idx
  on public.csp_reports (last_seen_at desc);

alter table public.csp_reports enable row level security;
revoke all on public.csp_reports from anon, authenticated;
grant select, insert, update on public.csp_reports to service_role;

-- Atomic upsert-and-increment. PostgREST cannot express "on conflict, add one
-- to a column", so the edge function calls this instead. SECURITY DEFINER with
-- a pinned search_path, EXECUTE granted to service_role only. The RLS suite
-- asserts the browser cannot reach it through the RPC path.
create or replace function public.record_csp_violation(
  p_fingerprint         text,
  p_document_path       text,
  p_effective_directive text,
  p_blocked_uri         text,
  p_source_file         text,
  p_line_number         integer
) returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.csp_reports (
    fingerprint, document_path, effective_directive,
    blocked_uri, source_file, line_number
  )
  values (
    p_fingerprint, p_document_path, p_effective_directive,
    p_blocked_uri, p_source_file, p_line_number
  )
  on conflict (fingerprint) do update
    set occurrences  = public.csp_reports.occurrences + 1,
        last_seen_at = now();
$$;

revoke all on function public.record_csp_violation(text,text,text,text,text,integer) from public, anon, authenticated;
grant execute on function public.record_csp_violation(text,text,text,text,text,integer) to service_role;

-- Retention, matching the five existing purge jobs. A violation nobody has
-- looked at in 90 days is either fixed or noise.
select cron.schedule(
  'purge-csp-reports',
  '45 3 * * *',
  $$DELETE FROM public.csp_reports WHERE last_seen_at < now() - interval '90 days'$$
);
