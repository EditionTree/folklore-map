-- Historical Context metadata for legend pages (Phase 2). All nullable —
-- backfilled gradually, entry by entry, same as detail/tags/date_added.
alter table public.legends
  add column if not exists origin_date text,
  add column if not exists earliest_record text,
  add column if not exists period text,
  add column if not exists historical_setting text,
  add column if not exists cultural_tradition text,
  add column if not exists origin_type text
    check (origin_type is null or origin_type in ('oral-tradition', 'literary', 'archaeological', 'historical-event')),
  add column if not exists dating_confidence text
    check (dating_confidence is null or dating_confidence in ('high', 'medium', 'low')),
  add column if not exists alt_names text[];
