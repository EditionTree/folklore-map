-- Retention for analytics_events and feedback. Applied 2026-08-21.
--
-- bug_reports and legend_submissions already had daily 03:00 cron deletion
-- (jobnames purge-old-bug-reports / purge-old-submissions) matching what the
-- Privacy Notice promises. analytics_events and feedback had neither
-- disclosure nor deletion, so the notice both omitted them and could not have
-- described them truthfully. This adds the deletion first, so the rewritten
-- notice describes something that actually happens.

-- feedback has no "when was this dealt with" timestamp, unlike bug_reports
-- (triaged_at) and legend_submissions (researched_at). Add one and stamp it
-- automatically the first time status moves off 'new', so retention runs from
-- actioning rather than from receipt -- a correction sitting unactioned for
-- five weeks should not vanish before it is read.
alter table public.feedback add column if not exists actioned_at timestamptz;

create or replace function public.stamp_feedback_actioned_at()
returns trigger
language plpgsql
as $$
begin
  if new.status is distinct from 'new' and new.actioned_at is null then
    new.actioned_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists feedback_stamp_actioned_at on public.feedback;
create trigger feedback_stamp_actioned_at
  before update on public.feedback
  for each row execute function public.stamp_feedback_actioned_at();

-- Rule A: feedback goes 30 days after it is actioned or rejected. Mirrors the
-- two existing jobs exactly, including the COALESCE fallback.
select cron.schedule(
  'purge-feedback-actioned',
  '0 3 * * *',
  $$DELETE FROM public.feedback
     WHERE status IN ('actioned','rejected')
       AND COALESCE(actioned_at, created_at) < now() - interval '30 days'$$
);

-- Rule B: backstop. Nothing survives 6 months whatever its status, so a
-- neglected row cannot be kept indefinitely and the notice can state a hard
-- maximum rather than an open-ended "until we deal with it".
select cron.schedule(
  'purge-feedback-backstop',
  '15 3 * * *',
  $$DELETE FROM public.feedback
     WHERE created_at < now() - interval '6 months'$$
);

-- analytics_events: 30 days from receipt. Raw pseudonymous rows with no status
-- lifecycle, so one age-based rule covers it. Note this permanently forgoes
-- year-over-year comparison; if that is wanted later, add a rollup table of
-- daily counts with no session_id, which is not personal data and can be kept.
select cron.schedule(
  'purge-analytics-events',
  '30 3 * * *',
  $$DELETE FROM public.analytics_events
     WHERE created_at < now() - interval '30 days'$$
);
