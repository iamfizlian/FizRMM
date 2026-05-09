# FizRMM Installation Guide

FizRMM runs locally with Docker Compose. The default stack starts the current app plus persistent Postgres:

- `postgres`: development PostgreSQL database seeded from `backend/migrations`
- `api`: FizRMM backend prototype at `http://127.0.0.1:8000`
- `portal`: React technician portal at `http://127.0.0.1:5173`

Keycloak, NATS, and OpenSearch are available as optional infrastructure services for later integration work.

This install can issue endpoint enrollment tokens and a Windows bootstrap script. Real remote/monitoring requires configuring MeshCentral, Zabbix, Wazuh, and Salt agent installer settings. See [Endpoint Deployment](ENDPOINT_DEPLOYMENT.md).

## 1. Prerequisites

Install Docker Desktop or Docker Engine with the Compose plugin.

Check that Docker is available:

```bash
docker --version
docker compose version
```

## 2. Start FizRMM

If you are using GitHub Codespaces, first see [GitHub Codespaces](CODESPACES.md) for forwarded ports and dev container setup.

From the repository root:

```bash
docker compose up --build
```

When startup is complete, open:

- Portal: `http://127.0.0.1:5173/`
- API health: `http://127.0.0.1:8000/health`

Expected log lines include:

```text
FizRMM API listening on http://0.0.0.0:8000
Local:   http://localhost:5173/
```

## 3. Verify The Install

In another terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "fizrmm-api",
  "store": "postgres"
}
```

List assets visible to an Acme technician:

```bash
curl -H 'X-FizRMM-Orgs: org_acme' http://127.0.0.1:8000/api/assets
```

Confirm cross-org access is blocked:

```bash
curl -i -H 'X-FizRMM-Orgs: org_acme' http://127.0.0.1:8000/api/assets/asset-globex-mac-01
```

Expected status:

```text
HTTP/1.0 403 Forbidden
```

Broker a fake MeshCentral session:

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-FizRMM-Orgs: org_acme' \
  -d '{"engine":"meshcentral"}' \
  http://127.0.0.1:8000/api/assets/asset-acme-win-01/remote-sessions
```

Expected response includes `session_id`, `engine`, and `launch_url`.

## 4. Stop Or Update

Stop the app:

```bash
docker compose down
```

Rebuild after dependency or Dockerfile changes:

```bash
docker compose build --no-cache
docker compose up
```

View service logs:

```bash
docker compose logs -f api
docker compose logs -f portal
```

## 5. Optional Infrastructure

The current UI already uses PostgreSQL through the API. Keycloak, NATS, and OpenSearch are behind the `infra` profile so the normal install stays lighter.

Create a local environment file:

```bash
cp .env.example .env
```

Start the infrastructure services:

```bash
docker compose --profile infra up -d keycloak nats opensearch
```

Service URLs:

- PostgreSQL: `localhost:5432`
- Keycloak: `http://127.0.0.1:8080`
- NATS: `localhost:4222`
- NATS monitoring: `http://127.0.0.1:8222`
- OpenSearch: `https://127.0.0.1:9200`

Stop the optional infrastructure services:

```bash
docker compose stop keycloak nats opensearch
docker compose rm -f keycloak nats opensearch
```

## 6. Integrated Lab Stack

The integrated lab stack starts FizRMM plus the backing capability engines together:

```bash
docker compose --profile full up --build
```

The `full` profile adds:

- Keycloak for identity.
- NATS JetStream for workflow/event streams.
- MeshCentral for remote access.
- Salt master for endpoint execution.
- Zabbix server/web with its own PostgreSQL database.
- Wazuh manager for endpoint inventory/log/security events.
- OpenSearch for search and retention.
- `fizrmm-init`, which waits for the backing services and writes `/runtime/fizrmm/integrations.json`.

This is currently a deployment scaffold. The init job writes the runtime contract consumed by `/api/integrations`; the next implementation step is making that init job call each subsystem API to create realms, tokens, groups, templates, ACLs, and index policies.

The Keycloak slice now creates:

- Realm: `fizrmm`
- Public OIDC client: `fizrmm-portal`
- Realm roles: `platform-admin`, `technician`
- Demo admin: `demo-admin` / `demo-admin-password`
- Demo technician: `demo-tech` / `demo-tech-password`

The API accepts Keycloak Bearer tokens when present and falls back to `X-FizRMM-*` headers for local development paths that have not moved to browser login yet.

## 7. Troubleshooting

### `docker: command not found`

Install Docker Desktop or Docker Engine with Compose, then restart your terminal.

### `Address already in use`

Another process is using `8000` or `5173`.

Stop the process, or change the host port mapping in `docker-compose.yml`:

```yaml
ports:
  - "5174:5173"
```

### Portal cannot connect to the API

Confirm the API is reachable from your host:

```bash
curl http://127.0.0.1:8000/health
```

The portal uses `FIZRMM_API_BASE` from `.env` or defaults to `http://127.0.0.1:8000`.

### Docker build cannot download packages

Confirm your host has internet access to npm and PyPI:

```bash
npm ping
python3 -m pip index versions fastapi
```

Then rebuild:

```bash
docker compose build --no-cache
```

### Reset everything

This stops containers and removes Compose-created volumes, including the PostgreSQL data volume:

```bash
docker compose --profile infra down --volumes
```
