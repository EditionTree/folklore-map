-- Add columns to mirror the extended legends.json schema (detail, tags, date_added).
-- Safe to run repeatedly: each column is only added if it does not already exist.
alter table public.legends
  add column if not exists detail text,
  add column if not exists tags text[],
  add column if not exists date_added date;
