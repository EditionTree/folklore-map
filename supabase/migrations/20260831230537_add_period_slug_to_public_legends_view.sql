-- Expose period_slug through the public read surface. Applied 2026-09-01
-- (recorded by Supabase as version 20260831230537, its clock being UTC).
--
-- period_slug is the controlled Explore Through Time period, one of the fifteen
-- slugs in periods.json or null. It is already visible to any visitor on every
-- legend page and on /legends/period/<slug>, so publishing it leaks nothing.
-- It is added here so the map can filter by period on the controlled field
-- rather than on the free-text `period` column, which mixes when a legend is
-- SET with when it was first written down. See content-style-guide.md under
-- "Assigning period_slug".
--
-- CREATE OR REPLACE, not DROP + CREATE: replace preserves the existing grants,
-- and this view's grants are load-bearing (anon reads it while holding no grant
-- on the base table, which is what makes the view a boundary). A drop would
-- silently take the anon SELECT with it and break the map.
--
-- Column order preserved and period_slug appended last, which is what CREATE OR
-- REPLACE requires. No security_invoker, matching 20260821160000: the view runs
-- with owner privileges deliberately. That migration's caveat still stands, and
-- is worth repeating because it is easy to lose: a definer view bypasses RLS on
-- the base table, which is harmless only while legends' single policy is a
-- blanket public-read SELECT with no row filtering. If row filtering is EVER
-- added to legends, replicate it here or this view leaks past it.
--
-- scripts/rls_regression_test.py asserts the exact column set and was updated in
-- the same change. It was run before, during and after: it passed at 32/32
-- beforehand, failed on "public_legends exposes exactly the expected columns"
-- immediately after this view change, and passed again once period_slug was
-- added to EXPECTED_PUBLIC_COLUMNS. That failure in the middle is the guard
-- working, and is the reason to widen the view and the test in one commit.
create or replace view public.public_legends as
select
  name, lat, lng, category, region, summary, source,
  tags, period, cultural_tradition, alt_names, period_slug
from public.legends;

comment on view public.public_legends is
  'Public read surface for the website. Adding a column to public.legends does '
  'not expose it here; it must be added to this view deliberately. Verified by '
  'scripts/rls_regression_test.py, which asserts the exact column set.';
