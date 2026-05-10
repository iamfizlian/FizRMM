# FizRMM

FizRMM is a greenfield internal MSP RMM control plane. The current build starts with the foundation from the architecture brief: portal-owned tenancy, canonical assets, multiple endpoint agent identities, brokered actions, and a device timeline.

This is an early development slice, not a production RMM yet. It gives you a working local portal, API, and PostgreSQL-backed control-plane store so the core shape can be exercised before wiring in Keycloak, MeshCentral, Salt, Zabbix, Wazuh, and OpenSearch for real.

## Quick Start With Docker

There is now one supported Docker startup path for an RMM lab install: start the full stack. The smaller API/portal-only Compose mode is no longer documented as an install because it cannot provide remote access, monitoring, logs, or script execution services by itself.

You need Docker Compose. From the repo root:

```bash
make full
```

That builds the local API and portal images serially, then starts PostgreSQL, the FizRMM portal/API, Keycloak, NATS, MeshCentral, Salt, Zabbix, Wazuh, OpenSearch, and the `fizrmm-init` job. The serialized Makefile path avoids Docker Compose concurrent-pull crashes and reduces temporary disk pressure on small hosts.

Open the UIs you need:

- FizRMM portal: `http://127.0.0.1:5173/`
- MeshCentral: `https://127.0.0.1:8443/`
- Zabbix: `http://127.0.0.1:8081/`
- Keycloak: `http://127.0.0.1:8080/`
- API health: `http://127.0.0.1:8000/health`

On a cloud VM, replace `127.0.0.1` with the public IP only after opening the required cloud security-list/firewall ports, or use SSH tunnels for those ports.

The Wazuh manager image is pinned to `wazuh/wazuh-manager:${WAZUH_MANAGER_VERSION:-4.14.5}` because Docker Hub does not publish a `latest` tag for that repository. Override `WAZUH_MANAGER_VERSION` when testing another published Wazuh tag.

Stop it:

```bash
docker compose down
```

For the full Docker setup guide, see [docs/INSTALL.md](docs/INSTALL.md). To run in GitHub Codespaces, see [docs/CODESPACES.md](docs/CODESPACES.md).

Endpoint deployment is partially implemented: the control plane can issue enrollment tokens and downloadable Windows and Linux bootstrap scripts. See [docs/ENDPOINT_DEPLOYMENT.md](docs/ENDPOINT_DEPLOYMENT.md) for endpoint enrollment details and the remaining subsystem-adapter work.

The staged path to a complete integrated RMM is tracked in [docs/INTEGRATION_PLAN.md](docs/INTEGRATION_PLAN.md).

## Smoke Checks

With Docker running:

```bash
curl http://127.0.0.1:8000/health
curl -H 'X-FizRMM-Orgs: org_acme' http://127.0.0.1:8000/api/assets
curl -i -H 'X-FizRMM-Orgs: org_acme' http://127.0.0.1:8000/api/assets/asset-globex-mac-01
```

The last command should return `403 Forbidden`; that is the tenant boundary test.

## Tests

Backend tests can be run through Make from the repository root or from `frontend/`:

```bash
make test-backend
```

From the repository root, you can also run the Python command directly:

```bash
PYTHONPATH=backend/src python3 -m unittest discover backend/tests
```

Build the frontend through Docker if your host does not have Node.js/npm installed. The same target works from the repository root or from `frontend/`:

```bash
make frontend-build
```

If you do have npm installed locally, you can also build directly. From the repository root:

```bash
cd frontend
npm run build
```

If your shell is already in `frontend/`, run only:

```bash
npm run build
```

## Current Slice

- Dockerized full lab stack for one-command startup with portal, API, PostgreSQL, Keycloak, MeshCentral, Salt, Zabbix, Wazuh, NATS, and OpenSearch.
- PostgreSQL-backed Docker install with seeded organizations, assets, agents, scripts, and timeline events.
- Dependency-light backend prototype with tenant-aware route contracts.
- Canonical domain model for orgs, assets, connector IDs, agent health, scripts, audit, and timeline events.
- PostgreSQL schema draft with row-level security policies.
- React portal shell scaffold for the technician experience.
- Integration readiness API and portal visibility for Keycloak, MeshCentral, Salt, Zabbix, and Wazuh configuration.
- Runtime integration readiness visibility for the backing services started by the Docker lab stack.

## Not Yet Implemented

- MeshCentral, Zabbix, Wazuh, or Salt server integration.
- Real remote control, monitoring, log collection, or script execution.
- Signed/package-managed Windows/macOS installers; Linux has a generated bootstrap shell script, but signed distro packages are still future work.

## Development-only minimal mode

The full stack above is the supported lab install. If you are only editing the API or portal and intentionally do not need the backing RMM service UIs, you can still start individual services with raw Docker Compose commands, but that mode is for development only and will not provide real remote-access/monitoring/logging capability.

## Tenant Simulation

Until Keycloak is wired in, the backend simulates technician claims with HTTP headers:

- `X-FizRMM-User`: technician identity, defaults to `demo-tech`
- `X-FizRMM-Orgs`: comma-separated allowed org IDs, defaults to `org_acme`
- `X-FizRMM-Role`: set to `platform-admin` for all-org access

Examples:

```bash
curl -H 'X-FizRMM-Orgs: org_globex' http://127.0.0.1:8000/api/assets
curl -H 'X-FizRMM-Role: platform-admin' http://127.0.0.1:8000/api/assets
```
