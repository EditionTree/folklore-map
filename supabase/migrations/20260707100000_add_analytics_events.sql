-- Lightweight, privacy-conscious event tracking (Phase 5 of the roadmap).
-- No personal data: just event type, what it relates to, and an optional
-- anonymous session id generated client-side (not tied to any account).
-- Same lockdown pattern as feedback/bug_reports/legend_submissions: inserts
-- only via the submit-event edge function's service-role key, never directly
-- from the browser.
create table if not exists public.analytics_events (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  event_type text not null check (event_type in (
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
    'product_clicked'
  )),
  legend_name text check (char_length(legend_name) <= 200),
  collection_slug text check (char_length(collection_slug) <= 200),
  period_slug text check (char_length(period_slug) <= 200),
  guide_id text check (char_length(guide_id) <= 200),
  -- Generic identifier for events that don't fit the columns above (an
  -- achievement id, a product/resource id, etc.).
  item_id text check (char_length(item_id) <= 200),
  referring_page text check (char_length(referring_page) <= 500),
  session_id text check (char_length(session_id) <= 100)
);

create index if not exists analytics_events_type_created_idx
  on public.analytics_events (event_type, created_at desc);

alter table public.analytics_events enable row level security;
revoke all on public.analytics_events from anon, authenticated;
