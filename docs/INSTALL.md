# FizRMM Installation Guide

This page is the step-by-step setup guide for the current FizRMM Docker workflow. There are two setup paths:

- **App setup**: starts the portal, API, and PostgreSQL database. This is the normal path and is enough to open the UI, inspect seeded assets, create organizations, and create endpoint enrollment commands.
- **Integration setup**: starts optional third-party service containers and then completes runtime setup from the portal. Use this only when you want local Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, or OpenSearch containers.


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

That command uses `docker-compose.app.yml`, pulls the latest code when possible, stops old application containers, rebuilds images, and starts the application. It runs in the foreground so you can see logs. Leave it running while you use the portal, or open another terminal for verification commands.

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

## 6. Optional Integration Containers

Skip this section if you only need the app UI/API/database. Use it when you want local third-party backing services.

The default `./fizrmm` command does **not** start Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, or OpenSearch. To start those containers, run:

```bash
./fizrmm integrations
```

What this command does:

1. Builds the FizRMM API and portal images used by the integration stack.
2. Starts `docker-compose.yml` with the `integrations` profile.
3. Starts the optional services plus `fizrmm-init`, which writes initial integration runtime config when the services are reachable.

Then complete setup from the portal:

1. Open `http://127.0.0.1:5173/`.
2. In the top bar, change the role selector from **Technician** to **Platform admin**.
3. Open **Integrations** in the left navigation.
4. If you are using the bundled local containers, click **Use deployment defaults + run** on each integration card.
5. If you are using existing external services, edit the service/bootstrap values first, then click **Save and run setup**.

What the setup buttons mean:

- **Save setup** writes the values only.
- **Save and run setup** writes the values and asks the API to run the deployment setup check.
- **Use deployment defaults + run** fills in the bundled local Docker defaults and runs the same setup check.

The API persists `/runtime/fizrmm/integrations.json` on the shared Compose volume. An integration moves from `configured` to `initialized` once its backing service endpoint is reachable from the API container. If it remains `setup_pending`, keep the integration stack running and click **Save and run setup** again after the service finishes starting.

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

### Reset everything

This stops containers and removes Compose-created volumes, including PostgreSQL data:

```bash
./fizrmm reset
```

Then start fresh:

```bash
./fizrmm
```
