-- Clears the function_search_path_mutable advisory raised against the trigger
-- added in 20260821140000. A function without a pinned search_path can be made
-- to resolve unqualified names against a schema the caller controls.
--
-- Empty search_path is safe here: the body references only NEW and now(), and
-- pg_catalog is always searched regardless. Re-verified after the change that
-- the trigger still stamps actioned_at on the first status change off 'new'.
create or replace function public.stamp_feedback_actioned_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status is distinct from 'new' and new.actioned_at is null then
    new.actioned_at := now();
  end if;
  return new;
end;
$$;
