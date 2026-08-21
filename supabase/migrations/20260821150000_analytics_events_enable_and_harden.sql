-- Turn the analytics pipeline on, and give it the protections it needs in the
-- same change. Applied 2026-08-21. Granting INSERT alone would have converted a
-- broken endpoint into a working, unauthenticated, service-role-backed public
-- write path, which is why this was deliberately held back from Stage 1.

-- 1. The grant missing since 2026-07-07. SELECT is needed too: the function
--    counts a session's recent events in order to rate-limit it.
grant insert, select on public.analytics_events to service_role;

-- 2. home_cta_click is fired by index.html but was in neither the edge
--    function's allowlist nor this constraint, so it 400'd and was dropped.
--    Homepage CTA data is exactly what the Stage 5 hierarchy work needs.
alter table public.analytics_events drop constraint analytics_events_event_type_check;
alter table public.analytics_events add constraint analytics_events_event_type_check
  check (event_type in (
    'legend_viewed', 'collection_viewed', 'period_viewed',
    'guide_viewed', 'guide_downloaded', 'kofi_link_clicked',
    'research_journal_clicked', 'achievement_unlocked', 'achievement_progress',
    'feedback_submitted', 'product_clicked', 'home_cta_click'
  ));

-- 3. Burst deduplication. The function computes a key from the identifying
--    fields plus a one-minute bucket; a unique index on it lets the insert use
--    ON CONFLICT DO NOTHING.
--
--    Deliberately a stored key rather than an expression index over
--    coalesce(...), because PostgREST can only name real columns as a conflict
--    target. Deliberately NOT partial either: Postgres cannot infer a partial
--    index from a bare ON CONFLICT (dedup_key), and NULLs are already treated
--    as distinct in a unique index, so rows without a session_id (and so
--    without a dedup key) never collide.
alter table public.analytics_events add column if not exists dedup_key text;
create unique index if not exists analytics_events_dedup_key_idx
  on public.analytics_events (dedup_key);

-- 4. Supports the per-session rate-limit count. The pre-existing index is
--    (event_type, created_at desc), which does not serve this lookup.
create index if not exists analytics_events_session_created_idx
  on public.analytics_events (session_id, created_at desc);
