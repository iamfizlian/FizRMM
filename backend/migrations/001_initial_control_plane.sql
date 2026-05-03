create table if not exists organizations (
    id text primary key,
    name text not null,
    status text not null default 'active',
    created_at timestamptz not null default now()
);

create table if not exists assets (
    id text primary key,
    org_id text not null references organizations(id),
    hostname text not null,
    operating_system text not null,
    site text,
    state text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists connector_identities (
    id bigserial primary key,
    org_id text not null references organizations(id),
    asset_id text not null references assets(id) on delete cascade,
    connector text not null,
    external_id text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (connector, external_id)
);

create table if not exists agent_health (
    id bigserial primary key,
    org_id text not null references organizations(id),
    asset_id text not null references assets(id) on delete cascade,
    agent text not null,
    version text not null,
    service_state text not null,
    last_seen_at timestamptz,
    update_channel text not null default 'stable',
    resource_status text not null default 'normal',
    updated_at timestamptz not null default now(),
    unique (asset_id, agent)
);

create table if not exists script_definitions (
    id text primary key,
    org_id text references organizations(id),
    name text not null,
    runtime text not null,
    revision integer not null default 1,
    approval_required boolean not null default false,
    body text not null,
    created_at timestamptz not null default now()
);

create table if not exists audit_events (
    id uuid primary key,
    org_id text not null references organizations(id),
    actor_user_id text not null,
    action text not null,
    asset_id text references assets(id),
    result text not null,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists timeline_events (
    id uuid primary key,
    org_id text not null references organizations(id),
    asset_id text not null references assets(id) on delete cascade,
    kind text not null,
    title text not null,
    body text not null,
    source text not null,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table assets enable row level security;
alter table organizations enable row level security;
alter table connector_identities enable row level security;
alter table agent_health enable row level security;
alter table script_definitions enable row level security;
alter table audit_events enable row level security;
alter table timeline_events enable row level security;

alter table organizations force row level security;
alter table assets force row level security;
alter table connector_identities force row level security;
alter table agent_health force row level security;
alter table script_definitions force row level security;
alter table audit_events force row level security;
alter table timeline_events force row level security;

create or replace function app_is_platform_admin()
returns boolean language sql stable as $$
    select coalesce(current_setting('app.platform_admin', true), 'false') = 'true';
$$;

create or replace function app_allowed_org_ids()
returns text[] language sql stable as $$
    select string_to_array(coalesce(current_setting('app.org_ids', true), ''), ',');
$$;

create or replace function app_can_access_org(target_org_id text)
returns boolean language sql stable as $$
    select app_is_platform_admin() or target_org_id = any(app_allowed_org_ids());
$$;

create policy organizations_tenant_select on organizations
    using (app_can_access_org(id));
create policy organizations_tenant_write on organizations
    with check (app_can_access_org(id));

create policy assets_tenant_select on assets
    using (app_can_access_org(org_id));
create policy assets_tenant_write on assets
    with check (app_can_access_org(org_id));

create policy connector_identities_tenant_select on connector_identities
    using (app_can_access_org(org_id));
create policy connector_identities_tenant_write on connector_identities
    with check (app_can_access_org(org_id));

create policy agent_health_tenant_select on agent_health
    using (app_can_access_org(org_id));
create policy agent_health_tenant_write on agent_health
    with check (app_can_access_org(org_id));

create policy script_definitions_tenant_select on script_definitions
    using (org_id is null or app_can_access_org(org_id));
create policy script_definitions_tenant_write on script_definitions
    with check (org_id is null or app_can_access_org(org_id));

create policy audit_events_tenant_select on audit_events
    using (app_can_access_org(org_id));
create policy audit_events_tenant_write on audit_events
    with check (app_can_access_org(org_id));

create policy timeline_events_tenant_select on timeline_events
    using (app_can_access_org(org_id));
create policy timeline_events_tenant_write on timeline_events
    with check (app_can_access_org(org_id));

create index if not exists idx_assets_org_id on assets(org_id);
create index if not exists idx_connector_identities_asset_id on connector_identities(asset_id);
create index if not exists idx_agent_health_asset_id on agent_health(asset_id);
create index if not exists idx_audit_events_org_created on audit_events(org_id, created_at desc);
create index if not exists idx_timeline_events_asset_created on timeline_events(asset_id, created_at desc);

create or replace function app_lookup_asset_org(target_asset_id text)
returns text
language sql
security definer
set search_path = public
stable
as $$
    select org_id from assets where id = target_asset_id;
$$;

create or replace function app_lookup_script_org(target_script_id text)
returns text
language sql
security definer
set search_path = public
stable
as $$
    select org_id from script_definitions where id = target_script_id;
$$;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'fizrmm_app') then
        create role fizrmm_app login password 'fizrmm-app-dev-password';
    end if;
end
$$;

grant usage on schema public to fizrmm_app;
grant select, insert, update, delete on all tables in schema public to fizrmm_app;
grant usage, select on all sequences in schema public to fizrmm_app;
grant execute on function app_lookup_asset_org(text) to fizrmm_app;
grant execute on function app_lookup_script_org(text) to fizrmm_app;
