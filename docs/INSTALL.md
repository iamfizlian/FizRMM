# FizRMM Installation Guide

This page is the step-by-step setup guide for the current FizRMM Docker workflow. The normal path starts the portal, API, PostgreSQL database, and bundled integration services.


## 1. Prerequisites

Install Docker Engine with the Compose plugin.

Check Docker:

```bash
docker --version
docker compose version
```

## 2. Start FizRMM

From the repository root, use one command:

```bash
./fizrmm
```

That command uses `docker-compose.yml` with the integrations profile, pulls the latest code when possible, stops old containers, rebuilds FizRMM images, starts the full stack, and runs `fizrmm-init` to write runtime integration config. It runs in the foreground so you can see logs. Leave it running while you use the portal, or open another terminal for verification commands.

Default services:

- `postgres`: FizRMM database.
- `api`: FizRMM backend.
- `portal`: FizRMM web UI.
- `keycloak`: SSO.
- `meshcentral`: remote access backing service.
- `zabbix-server` and `zabbix-web`: monitoring.
- `wazuh-manager`: security telemetry.
- `salt-master`: automation.
- `nats`: message bus.
- `opensearch`: indexed telemetry/search.
- `fizrmm-init`: one-shot integration initializer.

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
./fizrmm status
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

## 6. Integration Status And Overrides

The bundled integration stack is part of `./fizrmm`. The init container waits for the backing services, configures Keycloak, writes `/runtime/fizrmm/integrations.json`, and the API auto-initializes any missing runtime config from generated defaults.

Open **Integrations** in the portal to inspect live status. There is no manual setup sequence for the bundled stack. Platform admins can open **Override generated config** only when pointing FizRMM at external services or custom installers.

Bundled service UIs:

- MeshCentral: `https://127.0.0.1:8443/`
- Zabbix: `http://127.0.0.1:8081/`
- Keycloak: `http://127.0.0.1:8080/`

Install Docker Engine with Compose, then restart your terminal.

Confirm the API is reachable from the host:

Install Docker Engine with Compose, then restart your terminal.

### Docker build cannot download packages

Confirm the API is reachable from the host:

Another process is using `5173` or `8000`. Stop the process or change the host port mapping in `docker-compose.yml`.

### Docker build cannot download packages

Confirm the API is reachable from the host:

```bash
docker compose build --no-cache api portal
./fizrmm
```

The portal proxies `/api` to the API container. If direct API health works but the browser does not, check portal logs:

```bash
./fizrmm logs portal
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

The Compose file mounts PostgreSQL 18 volumes at `/var/lib/postgresql`, which lets the image create its major-version-specific data directory.

### Reset everything

This stops containers and removes Compose-created volumes, including PostgreSQL data:

```bash
./fizrmm reset
```

Then start fresh:

```bash
./fizrmm
```
