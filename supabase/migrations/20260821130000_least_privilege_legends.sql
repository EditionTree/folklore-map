-- Least privilege on public.legends.
--
-- anon and authenticated held SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER
-- and REFERENCES. RLS (one policy: "Public read access", SELECT, qual true)
-- made the DML grants inert -- an unfiltered DELETE as anon affects 0 rows,
-- because RLS makes every row invisible to it.
--
-- TRUNCATE is the exception. Postgres does NOT apply row-level security to
-- TRUNCATE: it is a table-level privilege, so RLS is not the control. Verified
-- inside a rolled-back transaction -- `set local role anon; truncate
-- public.legends;` succeeded and left 0 rows. The only thing preventing this in
-- production was PostgREST exposing no verb that reaches TRUNCATE, which is an
-- accident of the API surface, not a deliberate control.
--
-- The anon key is published in map.html, so this is a public role. It needs
-- exactly one privilege: SELECT.
--
-- SELECT is granted to authenticated as well as anon. There are no accounts
-- today, so authenticated is unused, but the goal here is removing destructive
-- privileges rather than restricting reads -- keeping SELECT on both means no
-- client can lose read access to the map.

revoke all on public.legends from anon, authenticated;
grant select on public.legends to anon, authenticated;
