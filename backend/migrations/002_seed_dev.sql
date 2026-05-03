select set_config('app.platform_admin', 'true', false);

insert into organizations (id, name, status)
values
    ('org_acme', 'Acme Medical', 'active'),
    ('org_globex', 'Globex Manufacturing', 'active')
on conflict (id) do nothing;

insert into assets (id, org_id, hostname, operating_system, site, state)
values
    ('asset-acme-win-01', 'org_acme', 'acme-billing-01', 'Windows 11 Pro', 'Acme HQ', 'active'),
    ('asset-acme-linux-01', 'org_acme', 'acme-file-01', 'Ubuntu Server 24.04', 'Acme HQ', 'degraded'),
    ('asset-globex-mac-01', 'org_globex', 'globex-design-07', 'macOS', 'Globex Design', 'active')
on conflict (id) do nothing;

insert into connector_identities (org_id, asset_id, connector, external_id, metadata)
select assets.org_id, assets.id, connector.connector, connector.connector || ':' || assets.id, '{"enrollment":"seed"}'::jsonb
from assets
cross join (
    values ('meshcentral'), ('salt'), ('wazuh'), ('zabbix')
) as connector(connector)
on conflict (connector, external_id) do nothing;

insert into agent_health (org_id, asset_id, agent, version, service_state, last_seen_at, update_channel, resource_status)
select assets.org_id, assets.id, agent.agent, 'seed-0.1', 'running', now(), 'lab', 'normal'
from assets
cross join (
    values ('meshcentral'), ('salt'), ('wazuh'), ('zabbix')
) as agent(agent)
on conflict (asset_id, agent) do nothing;

insert into script_definitions (id, org_id, name, runtime, revision, approval_required, body)
values
    ('script-disk-cleanup', null, 'Disk cleanup', 'powershell/bash', 1, false, '# placeholder cleanup script'),
    ('script-restart-print-spooler', 'org_acme', 'Restart print spooler', 'powershell', 3, true, 'Restart-Service Spooler')
on conflict (id) do nothing;

insert into timeline_events (id, org_id, asset_id, kind, title, body, source, details)
values
    (
        '11111111-1111-4111-8111-111111111111',
        'org_acme',
        'asset-acme-win-01',
        'inventory',
        'Asset enrolled',
        'Seeded asset graph with MeshCentral, Salt, Wazuh, and Zabbix connector IDs.',
        'portal',
        '{"connectors":["meshcentral","salt","wazuh","zabbix"]}'::jsonb
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'org_acme',
        'asset-acme-linux-01',
        'inventory',
        'Asset enrolled',
        'Seeded asset graph with MeshCentral, Salt, Wazuh, and Zabbix connector IDs.',
        'portal',
        '{"connectors":["meshcentral","salt","wazuh","zabbix"]}'::jsonb
    ),
    (
        '33333333-3333-4333-8333-333333333333',
        'org_globex',
        'asset-globex-mac-01',
        'inventory',
        'Asset enrolled',
        'Seeded asset graph with MeshCentral, Salt, Wazuh, and Zabbix connector IDs.',
        'portal',
        '{"connectors":["meshcentral","salt","wazuh","zabbix"]}'::jsonb
    )
on conflict (id) do nothing;
