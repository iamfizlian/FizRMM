# FizRMM

FizRMM is an MSP RMM control-plane application. The supported Docker startup runs the application itself: PostgreSQL, the API, and the technician portal. Optional third-party service containers are no longer part of the default install path.

## Quick Start

Use this path when you want the working FizRMM app only:

```bash
./fizrmm
```

When the containers finish starting, open:

```text
http://127.0.0.1:5173/
```

The default app stack is intentionally small: portal + API + PostgreSQL. It does **not** start Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, or OpenSearch. Those optional services are started only by the integrations workflow below.

On a cloud VM, replace `127.0.0.1` with the VM public IP after opening TCP `5173` in the cloud security rules and host firewall. The browser only needs the portal port; the portal proxies `/api` to the backend container.

## What Was Added In This Change

This update added four user-visible setup areas:

1. **One-command app startup** with `./fizrmm`, backed by `docker-compose.app.yml`.
2. **Endpoint enrollment** from the portal, including Windows `bootstrap.ps1` and Linux `bootstrap.sh` downloads.
3. **Integration setup from the portal**. Platform admins can save service/bootstrap values, apply bundled defaults, and run a deployment setup check from the UI.
4. **Optional local integration stack** via `./fizrmm integrations` for Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, and OpenSearch.

## Which Setup Path Should I Use?

| Goal | Command | What to do next |
| --- | --- | --- |
| Run the FizRMM app UI/API/database | `./fizrmm` | Open `http://127.0.0.1:5173/`. |
| Check app containers | `./fizrmm status` | Confirms portal, API, and Postgres are running. |
| Watch app logs | `./fizrmm logs` | Use `./fizrmm logs api` or `./fizrmm logs portal` for one service. |
| Start optional third-party services too | `./fizrmm integrations` | In the portal, switch to **Platform admin** → **Integrations** → **Use deployment defaults + run**. |
| Reset local app data | `./fizrmm reset` | Removes app containers and volumes, including PostgreSQL data. |

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

FizRMM ships bundled service defaults for Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, and OpenSearch. These defaults let the portal show you exactly what would be used, but they do not start the third-party products by themselves.

To run those products locally:

```bash
./fizrmm integrations
```

Then finish setup in the web UI:

1. Open `http://127.0.0.1:5173/`.
2. Change the role dropdown in the top bar to **Platform admin**.
3. Open **Integrations**.
4. For the bundled stack, click **Use deployment defaults + run** on each integration. If you use external services, edit the service/bootstrap fields first and click **Save and run setup**.
5. The API writes the runtime config to the shared Docker volume and marks an integration `initialized` after the service endpoint is reachable from the API container.

For endpoint enrollment, MeshCentral still needs a real MeshCentral device-group ID (`MESHCENTRAL_MESH_ID`) or an explicit Linux installer URL before the bootstrap can install the remote-control agent.

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
