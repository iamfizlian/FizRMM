# FizRMM Installation Guide

This is the normal install path for the FizRMM application. It starts the portal, API, and PostgreSQL database. It does **not** start the optional third-party integration containers unless you explicitly ask for them.

## 1. Prerequisites

Install Docker Engine with the Compose plugin.

Check Docker:

```bash
docker --version
docker compose version
```

## 2. Start FizRMM

From the repository root:

```bash
./fizrmm
```

That command uses `docker-compose.app.yml`, pulls the latest code when possible, stops old application containers, rebuilds images, and starts the application.

Default services:

- `postgres`: FizRMM database.
- `api`: FizRMM backend.
- `portal`: FizRMM web UI.

## 3. Open The UI

Local URL:

```text
http://127.0.0.1:5173/
```

API health URL:

```text
http://127.0.0.1:8000/health
```

On Oracle Cloud or another VM, either use an SSH tunnel or open TCP `5173` in the cloud security rules and host firewall.

SSH tunnel example from your workstation:

```bash
ssh -L 5173:127.0.0.1:5173 opc@<ORACLE_PUBLIC_IP>
```

Then open:

```text
http://127.0.0.1:5173/
```

If exposing it publicly, open only the portal port unless you specifically need direct API access:

```bash
sudo firewall-cmd --permanent --add-port=5173/tcp
sudo firewall-cmd --reload
```

## 4. Stop, Update, Restart

Stop the application:

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

These commands keep Docker volumes such as PostgreSQL data. To delete data, use the reset command below.

## 5. Verify The Install

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

## 6. Optional Integration Containers

The Compose file includes optional containers for Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, OpenSearch, and `fizrmm-init`. They are behind the `integrations` profile and are not part of the normal application install.

Only use this if you are developing integration adapters:

```bash
./fizrmm integrations
```

Open optional service UIs only when that profile is running:

- MeshCentral: `https://127.0.0.1:8443/`
- Zabbix: `http://127.0.0.1:8081/`
- Keycloak: `http://127.0.0.1:8080/`

## 7. Troubleshooting

### `docker: command not found`

Install Docker Engine with Compose, then restart your terminal.

### `Address already in use`

Another process is using `5173` or `8000`. Stop the process or change the host port mapping in `docker-compose.yml`.

### Portal cannot connect to the API

Confirm the API is reachable from the host:

```bash
curl http://127.0.0.1:8000/health
```

The portal proxies `/api` to the API container. If direct API health works but the browser does not, check portal logs:

```bash
docker compose logs -f portal
```

### Docker build cannot download packages

Confirm Docker builds have internet access to npm and PyPI, then rebuild:

```bash
docker compose build --no-cache api portal
./fizrmm
```

### Docker reports `no space left on device`

Remove unused BuildKit cache and dangling images:

```bash
make docker-prune
```

Inspect Docker usage before deleting volumes that may contain data:

```bash
docker system df
docker volume ls
```

### Reset everything

This stops containers and removes Compose-created volumes, including PostgreSQL data:

```bash
docker compose down --volumes --remove-orphans
```

Then start fresh:

```bash
./fizrmm
```
