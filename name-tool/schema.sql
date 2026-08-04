-- ============================================================================
-- "Name Through Time" — schema (NOT YET APPLIED)
-- Kept as a standalone file during the prototype phase. When the concept is
-- proven, move this into supabase/migrations/<timestamp>_add_name_tool.sql and
-- apply it (on a Supabase branch first).
--
-- Read tables: RLS on + a SELECT policy + GRANT SELECT to anon. Miss the GRANT
-- and the anon REST call 401s even with a policy (the documented gotcha).
-- Write table (name_searches): fully locked down, inserts only via the
-- submit-name-search edge function's service-role key — mirrors analytics_events.
-- ============================================================================

-- ── Read tables ────────────────────────────────────────────────────────────
create table if not exists public.names (
  id bigint generated always as identity primary key,
  slug text unique not null,
  canonical_name text not null,
  origin_language text,
  historical_root text,
  meaning_summary text,
  historical_notes text,
  confidence text check (confidence in ('high','medium','low')),
  reviewed_at timestamptz default now()
);

create table if not exists public.name_variants (
  id bigint generated always as identity primary key,
  name_id bigint not null references public.names(id) on delete cascade,
  variant text not null,               -- store lowercased
  variant_type text                    -- 'nickname' | 'spelling' | 'formal' | ...
);
create index if not exists name_variants_variant_idx on public.name_variants (lower(variant));

create table if not exists public.name_pronunciations (
  id bigint generated always as identity primary key,
  name_id bigint not null references public.names(id) on delete cascade,
  locale text default 'en-GB',
  display_pronunciation text,          -- e.g. 'shuh-vawn'
  phoneme_sequence text[]              -- e.g. {sh,u,v,aw,n}
);

create table if not exists public.historical_name_forms (
  id bigint generated always as identity primary key,
  name_id bigint not null references public.names(id) on delete cascade,
  language text,                       -- 'Old English'
  period text,
  historical_form text,                -- 'Ēadweard' or NULL for no equivalent
  relationship_type text,              -- 'direct_ancestor' | 'no_direct_equivalent' | ...
  status text check (status in ('attested','reconstructed','reviewed')),
  explanation text
);

create table if not exists public.script_systems (
  id bigint generated always as identity primary key,
  slug text unique not null,           -- 'younger-futhark' | 'ogham'
  display_name text not null,
  period text,
  disclaimer text
);

create table if not exists public.script_mappings (
  id bigint generated always as identity primary key,
  script_system_id bigint not null references public.script_systems(id) on delete cascade,
  input_sound text not null,           -- 'th', 'g', 'aw', ...
  output_character text not null,      -- the glyph
  priority int default 0,
  notes text
);

-- ── Write-only table (locked down) ──────────────────────────────────────────
create table if not exists public.name_searches (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  query_raw text check (char_length(query_raw) <= 200),
  matched_name_id bigint references public.names(id) on delete set null,
  matched boolean not null default false,
  session_id text check (char_length(session_id) <= 100)
);
-- Expansion-queue query: which unmatched names are people asking for?
create index if not exists name_searches_unmatched_idx
  on public.name_searches (matched, created_at desc);

-- ── RLS + grants ────────────────────────────────────────────────────────────
-- Read tables: readable by anon.
do $$
declare t text;
begin
  foreach t in array array[
    'names','name_variants','name_pronunciations',
    'historical_name_forms','script_systems','script_mappings'
  ] loop
    execute format('alter table public.%I enable row level security;', t);
    execute format('drop policy if exists %I on public.%I;', t||'_anon_read', t);
    execute format('create policy %I on public.%I for select to anon using (true);', t||'_anon_read', t);
    execute format('grant select on public.%I to anon;', t);  -- REQUIRED alongside the policy
  end loop;
end $$;

-- Write table: no anon/authenticated access at all.
alter table public.name_searches enable row level security;
revoke all on public.name_searches from anon, authenticated;
