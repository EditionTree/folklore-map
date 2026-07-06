-- "Have Your Say" feedback (What's New page). Mirrors bug_reports/legend_submissions:
-- anonymous inserts land here via the submit-feedback edge function (service role),
-- never directly from the browser.
create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  feedback_type text not null check (feedback_type in
    ('bug','missing_legend','incorrect_info','feature_suggestion','source_suggestion','general')),
  message text not null check (char_length(message) <= 2000),
  page_url text check (char_length(page_url) <= 500),
  related_legend text check (char_length(related_legend) <= 200),
  related_collection text check (char_length(related_collection) <= 200),
  contact_email text check (char_length(contact_email) <= 320),
  status text not null default 'new' check (status in
    ('new','reviewed','actioned','rejected','needs_follow_up')),
  flagged boolean not null default false,
  flagged_reason text
);

alter table public.feedback enable row level security;

-- No policies are defined, so RLS denies all access by default. Belt-and-braces:
-- explicitly revoke the table-level grants too, since anon/authenticated must never
-- read or write this table directly — only the submit-feedback edge function
-- (using the service-role key) may insert.
revoke all on public.feedback from anon, authenticated;

-- Defensive backfill: bug_reports/legend_submissions were created directly against
-- the database rather than through a tracked migration, so their current lockdown
-- (RLS enabled, no anon/authenticated grants) exists only as untracked dashboard
-- state. Re-assert it here so the posture is captured in version control too.
revoke all on public.bug_reports from anon, authenticated;
revoke all on public.legend_submissions from anon, authenticated;
