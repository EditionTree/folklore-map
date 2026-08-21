-- A dedicated public read surface for the website. Applied 2026-08-21.
--
-- The browser makes exactly one query against legends (map.html), selecting 11
-- of its 21 columns. Everything else is statically generated from legends.json
-- at build time, so nothing else reads this table at runtime.
--
-- All 21 columns are public-safe today, so this plugs no leak. Its value is
-- that the next column added to legends is NOT public by default; it has to be
-- added here deliberately. scripts/rls_regression_test.py asserts the exact
-- column set, so a widened view fails the suite.
--
-- The view intentionally runs with owner privileges (no security_invoker), so
-- anon can read it while holding no grant on the base table. That is what makes
-- it a boundary rather than a convenience.
--
-- CAVEAT, and the reason Supabase's linter flags this as security_definer_view:
-- a definer view bypasses row-level security on the base table. That is
-- harmless today because legends' only policy is a blanket public-read SELECT
-- with no row filtering. If row filtering is EVER added to legends, it must be
-- replicated in this view or the view will leak past it.
create or replace view public.public_legends as
select
  name, lat, lng, category, region, summary, source,
  tags, period, cultural_tradition, alt_names
from public.legends;

comment on view public.public_legends is
  'Public read surface for the website. Adding a column to public.legends does '
  'not expose it here; it must be added to this view deliberately. Verified by '
  'scripts/rls_regression_test.py, which asserts the exact column set.';

grant select on public.public_legends to anon, authenticated;
