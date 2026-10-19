-- User-controlled profile presentation fields.  Authentication identity stays
-- in Auth0; this table never changes a verified sign-in email or stores any
-- EEG/ECG waveform data.
create table if not exists public.profile_preferences (
  auth0_subject text primary key,
  display_name text check (char_length(display_name) between 1 and 80),
  contact_email text check (char_length(contact_email) between 3 and 254),
  -- A client-compressed PNG/JPEG/WebP data URL, restricted by the API to a
  -- small avatar-sized image.  It is not made public or directly readable by
  -- browser database credentials.
  avatar_data text check (char_length(avatar_data) <= 500000),
  updated_at timestamptz not null default now()
);

alter table public.profile_preferences enable row level security;

-- The Vercel server uses its service-role key after checking the Auth0 JWT.
-- Browser clients have no direct access to another user's profile fields.
revoke all on table public.profile_preferences from anon, authenticated;
