# FizRMM

FizRMM is a greenfield internal MSP RMM control plane. The current build starts with the foundation from the architecture brief: portal-owned tenancy, canonical assets, multiple endpoint agent identities, brokered actions, and a device timeline.

This is an early development slice, not a production RMM yet. It gives you a working local portal, API, and PostgreSQL-backed control-plane store so the core shape can be exercised before wiring in Keycloak, MeshCentral, Salt, Zabbix, Wazuh, and OpenSearch for real.

## Quick Start With Docker

You need Docker Compose. From the repo root:

```bash
docker compose up --build
```

To start the integrated lab stack scaffold, use the serialized-pull command below. The `COMPOSE_PARALLEL_LIMIT=1` prefix works around a Docker Compose crash that can happen when the full profile pulls many images concurrently in Codespaces.

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full up --build
```

You can also run `make full`.

The `full` profile adds Keycloak, NATS, MeshCentral, Salt, Zabbix, Wazuh, OpenSearch, and a `fizrmm-init` job that writes runtime integration config for the API.

The Wazuh manager image is pinned to `wazuh/wazuh-manager:${WAZUH_MANAGER_VERSION:-4.14.5}` because Docker Hub does not publish a `latest` tag for that repository. Override `WAZUH_MANAGER_VERSION` when testing another published Wazuh tag.

Open:

- Portal: `http://127.0.0.1:5173/`
- API health: `http://127.0.0.1:8000/health`

Stop it:

```bash
docker compose down
```

For the full Docker setup guide, see [docs/INSTALL.md](docs/INSTALL.md). To run in GitHub Codespaces, see [docs/CODESPACES.md](docs/CODESPACES.md).

Endpoint deployment is partially implemented: the control plane can issue enrollment tokens and a Windows bootstrap script. See [docs/ENDPOINT_DEPLOYMENT.md](docs/ENDPOINT_DEPLOYMENT.md) for how PCs are enrolled and what still needs real subsystem integration.

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

Backend tests run directly with Python:

```bash
PYTHONPATH=backend/src python3 -m unittest discover backend/tests
```

Build the frontend through Docker if your host does not have Node.js/npm installed. The same target works from the repository root or from `frontend/`:

```bash
make frontend-build
```

If you do have npm installed locally, you can also build from `frontend/`:

```bash
cd frontend
npm run build
```

## Current Slice

- Dockerized backend and portal for one-command local startup.
- PostgreSQL-backed Docker install with seeded organizations, assets, agents, scripts, and timeline events.
- Dependency-light backend prototype with tenant-aware route contracts.
- Canonical domain model for orgs, assets, connector IDs, agent health, scripts, audit, and timeline events.
- PostgreSQL schema draft with row-level security policies.
- React portal shell scaffold for the technician experience.
- Integration readiness API and portal visibility for Keycloak, MeshCentral, Salt, Zabbix, and Wazuh configuration.
- Optional Docker Compose profile for Keycloak, NATS, and OpenSearch.

## Not Yet Implemented

- MeshCentral, Zabbix, Wazuh, or Salt server integration.
- Real remote control, monitoring, log collection, or script execution.
- Signed/package-managed Windows/macOS/Linux installers.

## Optional Infrastructure

The current app starts Postgres by default. When you are ready to start the heavier future integration services:

```bash
cp .env.example .env
docker compose --profile infra up -d keycloak nats opensearch
```

The compose stack is the next integration target and is intentionally a development baseline, not production hardening.

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
