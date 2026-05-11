# FizRMM

FizRMM is an MSP RMM control-plane application. The supported Docker startup runs the application itself: PostgreSQL, the API, and the technician portal. Optional third-party service containers are no longer part of the default install path.

## Start The Application

From the repository root:

```bash
./fizrmm
```

Open the UI:

```text
http://127.0.0.1:5173/
```

On a cloud VM, replace `127.0.0.1` with the VM public IP after opening TCP `5173` in the cloud security rules and host firewall. The browser only needs the portal port; the portal proxies `/api` to the backend container.

## Stop, Update, Restart

Stop the running application:

```bash
./fizrmm stop
```

Use the same command after GitHub updates are available; it pulls, rebuilds, and restarts the app:

```bash
./fizrmm
```

Restart without pulling code:

```bash
./fizrmm restart
```

## What Starts By Default

`./fizrmm` uses `docker-compose.app.yml` and starts only the working FizRMM application services:

- `postgres`: application database with seeded organizations, assets, scripts, and timeline data.
- `api`: FizRMM backend at `http://127.0.0.1:8000`.
- `portal`: FizRMM web UI at `http://127.0.0.1:5173`.

The portal includes the current application workflows: assets, endpoint enrollment, automation requests, integration readiness, alerts, logs, and access/org creation.

## Optional External Service Containers

The repository still includes optional Compose definitions for Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, OpenSearch, and `fizrmm-init`, but they are behind the `integrations` profile and are not required to run the application UI.

Only start those containers if you are explicitly working on subsystem integration code:

```bash
./fizrmm integrations
```

Those services are scaffolding for future adapters. They are not required for normal app startup.

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

If you do have npm installed locally, you can also build directly:

```bash
cd frontend
npm run build
```

## Current Capabilities

- Dockerized app startup for portal, API, and PostgreSQL.
- Tenant-aware backend route contracts.
- PostgreSQL-backed organizations, assets, connector identities, agent health, scripts, audit, timeline, and endpoint enrollment.
- Portal workflows for assets, enrollment bootstrap downloads, automation requests, integration readiness, alerts, logs, and organization creation.
- Windows and Linux endpoint bootstrap script generation.

## Still In Progress

- Real MeshCentral, Zabbix, Wazuh, and Salt adapters.
- Production remote control, monitoring, log collection, and script execution.
- Signed/package-managed endpoint installers.

## Tenant Simulation

Until real SSO is wired in, the backend simulates technician claims with HTTP headers:

- `X-FizRMM-User`: technician identity, defaults to `demo-tech`
- `X-FizRMM-Orgs`: comma-separated allowed org IDs, defaults to `org_acme`
- `X-FizRMM-Role`: set to `platform-admin` for all-org access

Examples:

```bash
curl -H 'X-FizRMM-Orgs: org_globex' http://127.0.0.1:8000/api/assets
curl -H 'X-FizRMM-Role: platform-admin' http://127.0.0.1:8000/api/orgs
```

For detailed setup and troubleshooting, see [docs/INSTALL.md](docs/INSTALL.md). For Codespaces, see [docs/CODESPACES.md](docs/CODESPACES.md). Endpoint deployment details are in [docs/ENDPOINT_DEPLOYMENT.md](docs/ENDPOINT_DEPLOYMENT.md).
