# FizRMM Installation Guide

FizRMM's supported Docker install starts the full lab stack. There is not a separate "working" lightweight install: the portal alone cannot provide remote access, monitoring, logs, or execution without the backing services.

The full stack includes:

- `portal`: FizRMM technician portal at `http://127.0.0.1:5173`
- `api`: FizRMM backend at `http://127.0.0.1:8000`
- `postgres`: FizRMM control-plane database
- Keycloak, NATS, MeshCentral, Salt, Zabbix, Wazuh, OpenSearch, and `fizrmm-init`

Endpoint enrollment can generate both Windows PowerShell and Linux shell bootstrap downloads. Real remote/monitoring still depends on finishing the subsystem adapters and configuring agent installer URLs. See [Endpoint Deployment](ENDPOINT_DEPLOYMENT.md).

## 1. Prerequisites

Install Docker Engine with the Compose plugin. On small cloud VMs, give Docker enough disk for the full lab images.

Check that Docker is available:

```bash
docker --version
docker compose version
```

## 2. Start FizRMM

From the repository root:

```bash
make full
```

The Makefile builds the local `api` and `portal` images one at a time before starting the full stack. This avoids Docker Compose concurrent-pull crashes and reduces temporary image-export disk pressure.

Equivalent raw Compose sequence:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full build api
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full build portal
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full up --no-build
```

## 3. Open The UIs

Local URLs:

- FizRMM portal: `http://127.0.0.1:5173/`
- MeshCentral remote access UI: `https://127.0.0.1:8443/`
- Zabbix UI: `http://127.0.0.1:8081/`
- Keycloak UI: `http://127.0.0.1:8080/`
- API health: `http://127.0.0.1:8000/health`

On Oracle Cloud or another VM, either use SSH tunnels or open the matching cloud ingress and Linux firewall ports. SSH tunnel example from your workstation:

```bash
ssh \
  -L 5173:127.0.0.1:5173 \
  -L 8443:127.0.0.1:8443 \
  -L 8081:127.0.0.1:8081 \
  -L 8080:127.0.0.1:8080 \
  opc@<ORACLE_PUBLIC_IP>
```

Then open the `127.0.0.1` URLs above on your workstation.

## 4. Verify The Install

In another terminal:

```bash
curl http://127.0.0.1:8000/health
docker compose ps
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

## 5. Stop Or Update

Stop the stack:

```bash
docker compose down
```

View service logs:

```bash
docker compose logs -f api
docker compose logs -f portal
docker compose logs -f meshcentral
docker compose logs -f zabbix-web
```

## 6. Development-only Minimal Mode

The full stack is the install path. Raw `docker compose up --build` also starts the same stack now. If you manually target only `postgres`, `api`, and `portal`, that is a developer-only control-plane mode and will not provide remote access, monitoring, Wazuh logs, or Salt execution.

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

The Compose portal proxies `/api` to the API container. If direct API health works but the browser does not, check the portal container logs with `docker compose logs -f portal`.

### Docker build cannot download packages

Confirm Docker builds have internet access to npm and PyPI. If your host has npm/Python tooling, these checks are useful:

```bash
npm ping
python3 -m pip index versions fastapi
```

Then rebuild:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose build --no-cache api portal
```

### Docker Compose concurrent pull crash

If raw Compose crashes with `fatal error: concurrent map writes` while pulling images, use the Makefile shortcut. It serializes local image builds and starts Compose with serialized pull operations:

```bash
make full
```

The equivalent raw Compose sequence is:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full build api
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full build portal
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full up --no-build
```

### Docker reports `no space left on device` during `make full`

The lab stack pulls several large upstream images. If Docker's storage directory is already close to full, BuildKit may still fail while exporting images or installing frontend dependencies into the `frontend_node_modules` volume. First remove unused Docker build cache and dangling images:

```bash
make docker-prune
```

If you still need space, inspect Docker usage before deleting volumes that may contain development data:

```bash
docker system df
docker volume ls
```

If frontend dependencies are stale or partially installed after a failed run, remove only the portal dependency volume and start again:

```bash
docker compose down
docker volume rm fizrmm_frontend_node_modules
make full
```

Only after saving any data you need, remove stopped containers and unused images/volumes with Docker's broader prune commands.

### PostgreSQL 18 volume layout error

If PostgreSQL exits with a message about data in `/var/lib/postgresql/data` or an unused mount/volume, remove the old development volume and start again:

```bash
docker compose down --volumes
make full
```

The Compose file mounts PostgreSQL 18 volumes at `/var/lib/postgresql`, which lets the image create its major-version-specific data directory.

### Reset everything

This stops containers and removes Compose-created volumes, including the PostgreSQL data volumes:

```bash
docker compose down --volumes
```
