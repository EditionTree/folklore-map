-- Controlled Explore Through Time period for each legend. Nullable, and null is
-- a correct finished answer, not a backfill gap: a legend whose setting cannot
-- be dated (undated oral tradition such as Brownie or Redcap) belongs on no
-- period page at all.
--
-- This is deliberately NOT the same fact as the existing free-text `period`
-- column. `period` mixes when a legend is SET with when it was first written
-- down, in 626 distinct values across 710 entries, which is why only 8 of them
-- ever matched a period page. `period_slug` carries the setting only. The
-- record axis stays in `earliest_record`.
--
-- The enum mirrors the `slug` values in the repo's periods.json. Assignment
-- rules are in content-style-guide.md under "Assigning period_slug".
-- Note `anglo-saxon-england` is absent on purpose: it was renamed to
-- `early-medieval-britain` on 2026-08-27 so the 600 to 1066 window could cover
-- early Christian Ireland and Pictish/Gaelic Scotland, which the England-only
-- title excluded.
-- Applied to production 2026-08-31 as migration 20260831181305; this file was
-- renamed from 20260827120000 to match the version Supabase recorded.
alter table public.legends
  add column if not exists period_slug text
    check (period_slug is null or period_slug in (
      'prehistoric-britain',
      'bronze-age',
      'iron-age',
      'roman-britain',
      'sub-roman-britain',
      'early-medieval-britain',
      'viking-age',
      'norman-britain',
      'medieval-britain',
      'tudor-britain',
      'stuart-britain',
      'georgian-britain',
      'victorian-britain',
      'edwardian-britain',
      'modern-folklore'
    ));
