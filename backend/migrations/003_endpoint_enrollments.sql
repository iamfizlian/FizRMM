create table if not exists endpoint_enrollments (
    id uuid primary key,
    org_id text not null references organizations(id),
    site text not null,
    token text not null unique,
    status text not null default 'active',
    created_by text not null,
    asset_id text references assets(id),
    config jsonb not null default '{}'::jsonb,
    expires_at timestamptz not null,
    claimed_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);

alter table endpoint_enrollments enable row level security;
alter table endpoint_enrollments force row level security;

create policy endpoint_enrollments_tenant_select on endpoint_enrollments
    using (app_can_access_org(org_id));
create policy endpoint_enrollments_tenant_write on endpoint_enrollments
    with check (app_can_access_org(org_id));

create or replace function app_lookup_enrollment_org(target_token text)
returns text
language sql
security definer
set search_path = public
stable
as $$
    select org_id from endpoint_enrollments where token = target_token;
$$;

grant select, insert, update, delete on endpoint_enrollments to fizrmm_app;
grant execute on function app_lookup_enrollment_org(text) to fizrmm_app;

create index if not exists idx_endpoint_enrollments_org_created on endpoint_enrollments(org_id, created_at desc);
create index if not exists idx_endpoint_enrollments_token on endpoint_enrollments(token);
