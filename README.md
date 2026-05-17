# FizRMM

FizRMM is an MSP RMM control-plane application. The supported Docker startup runs the portal, API, PostgreSQL, and the bundled integration stack: Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, and OpenSearch.

## Quick Start

Use this path to start the full working FizRMM stack:

```bash
./fizrmm
```

When the containers finish starting, open:

```text
http://127.0.0.1:5173/
```

On a cloud VM, replace `127.0.0.1` with the VM public IP after opening TCP `5173` in the cloud security rules and host firewall. The browser only needs the portal port; the portal proxies `/api` to the backend container.

## What Was Added In This Change

This update added four user-visible setup areas:

1. **One-command full-stack startup** with `./fizrmm`, backed by `docker-compose.yml`.
2. **Endpoint enrollment** from the portal, including Windows `bootstrap.ps1` and Linux `bootstrap.sh` downloads.
3. **Automatic integration initialization**. The `fizrmm-init` container writes runtime config for the bundled integration stack.
4. **Optional integration overrides** from the portal for deployments that point FizRMM at external services.

## Which Setup Path Should I Use?

| Goal | Command | What to do next |
| --- | --- | --- |
| Run FizRMM | `./fizrmm` | Open `http://127.0.0.1:5173/`. |
| Check containers | `./fizrmm status` | Confirms the portal, API, database, and integration services are running. |
| Watch app logs | `./fizrmm logs` | Use `./fizrmm logs api` or `./fizrmm logs portal` for one service. |
| Start integrations | `./fizrmm integrations` | Compatibility alias for `./fizrmm`. |
| Reset local app data | `./fizrmm reset` | Removes containers and volumes, including PostgreSQL and integration data. |

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

`./fizrmm` uses `docker-compose.yml` with the integrations profile and starts:

- `postgres`: application database with seeded organizations, assets, scripts, and timeline data.
- `api`: FizRMM backend at `http://127.0.0.1:8000`.
- `portal`: FizRMM web UI at `http://127.0.0.1:5173`.
- `fizrmm-init`: one-shot initialization for runtime integration config.
- `keycloak`, `meshcentral`, `zabbix-server`, `zabbix-web`, `wazuh-manager`, `salt-master`, `opensearch`, and `nats`.

The portal includes the current application workflows: assets, endpoint enrollment, automation requests, integration readiness, alerts, logs, and access/org creation.

## Integration Overrides

The bundled stack initializes automatically. Use the portal **Integrations** view only when you want to override generated config for external services or custom agent installers. The API persists `/runtime/fizrmm/integrations.json` on the shared Docker volume.

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
