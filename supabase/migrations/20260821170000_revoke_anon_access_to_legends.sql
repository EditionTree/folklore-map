-- Remove anonymous access to the base table. Applied 2026-08-21, and only
-- after map.html had been deployed reading public_legends and verified live,
-- so there was no window in which the map could not read.
--
-- anon and authenticated keep SELECT on public.public_legends, which runs with
-- owner privileges and so needs no grant here. From this point the published
-- anon key cannot name public.legends at all: both select=name and select=*
-- return 42501, and selecting a column the view omits returns 42703.
revoke all on public.legends from anon, authenticated;
