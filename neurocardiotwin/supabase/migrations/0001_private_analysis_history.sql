-- Private metadata history for authenticated NeuroCardioTwin users.
-- Raw EEG/ECG samples, uploads, tokens, email addresses and Auth0 subjects do
-- not belong in this table.
create table if not exists public.analysis_history (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  analysis_type text not null check (analysis_type in ('seizure', 'arrhythmia', 'forecast')),
  session_label text not null,
  model_summary jsonb not null,
  decision_text text,
  source_titles jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists analysis_history_profile_created_idx
  on public.analysis_history (profile_id, created_at desc);

alter table public.analysis_history enable row level security;

-- The application uses a server-only Supabase service key. Browser clients
-- receive no direct table grants, so history is reachable only through an
-- Auth0-verified API route that filters by the token subject.
revoke all on table public.analysis_history from anon, authenticated;
