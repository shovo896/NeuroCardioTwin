-- Repair server-side persistence access for the Auth0-verified Vercel API.
-- Browser roles remain explicitly denied; only the server's service_role can
-- create and retrieve private profile presentation data and history metadata.

grant usage on schema public to service_role;

grant select, insert, update on table public.profiles to service_role;
grant select, insert, update on table public.profile_preferences to service_role;
grant select, insert on table public.analysis_history to service_role;

-- These tables are optional in early project setups.  If they exist, allow
-- the server to read organisation labels and record minimal audit events.
do $$
begin
  if to_regclass('public.organization_memberships') is not null then
    grant select on table public.organization_memberships to service_role;
  end if;
  if to_regclass('public.organizations') is not null then
    grant select on table public.organizations to service_role;
  end if;
  if to_regclass('public.audit_events') is not null then
    grant insert on table public.audit_events to service_role;
  end if;
end
$$;
