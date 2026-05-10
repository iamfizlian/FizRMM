# GitHub Codespaces

FizRMM can run in a GitHub Codespace for development and demos. The dev container uses the GitHub Codespaces universal image, installs Python and frontend dependencies, and exposes the app ports so the existing Compose stack can run inside the Codespace.

## Start a Codespace

1. Open the repository in GitHub.
2. Select **Code** → **Codespaces** → **Create codespace on current branch**.
3. Wait for the dev container `postCreateCommand` to finish. It creates `.venv`, installs `backend/requirements.txt`, and runs `npm ci` in `frontend/`.

## Run the default stack

The universal Codespaces image includes Docker tooling, so no extra Docker devcontainer feature is required. From the Codespaces terminal:

```bash
docker compose up --build
```

Open the forwarded ports panel and use:

- `5173` for the FizRMM portal. This is the web GUI.
- `8000` for the FizRMM API, if you want to inspect API responses directly.
- `5432` for PostgreSQL, if you need direct database access.

The portal should be available through the Codespaces forwarded URL for port `5173`. In Docker Compose, the portal calls the API through Vite's dev proxy, so browser requests use the same forwarded `5173` origin and do not need a separate public API URL.

Once the portal opens, you can exercise the current RMM control-plane workflows:

- Select an asset and click **Broker remote** or **Broker jump** to create a remote-session request and timeline entry.
- Open **Enroll endpoint** to generate a one-time endpoint token, bootstrap URL, and PowerShell command.
- Open **Automation** to queue a script request for the selected asset.
- Open **Integrations** to inspect which backing services still need real subsystem configuration.

If PostgreSQL exits with a `/var/lib/postgresql/data` volume-layout error, reset the development volumes and start the stack again:

```bash
docker compose down --volumes
docker compose up --build
```

## Run the full lab scaffold

The full profile is heavier and may need a larger Codespaces machine size because it starts Keycloak, NATS, MeshCentral, Salt, Zabbix, Wazuh, and OpenSearch in addition to the app:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full up --build
```

You can also run:

```bash
make full
```

The `COMPOSE_PARALLEL_LIMIT=1` prefix is intentional. Some Codespaces Docker Compose builds can crash with `fatal error: concurrent map writes` while pulling many full-profile images at once. Serializing Compose image operations avoids that Docker Compose bug.

The full profile pins Wazuh manager to `wazuh/wazuh-manager:${WAZUH_MANAGER_VERSION:-4.14.5}` because Docker Hub does not publish a `latest` tag for that image. Override `WAZUH_MANAGER_VERSION` only with a published Wazuh manager tag.

Forwarded ports include:

- `8080` for Keycloak.
- `8081` for Zabbix Web.
- `8222` for NATS monitoring.
- `8443` for MeshCentral.
- `9200` for OpenSearch.

## Run tests without Docker

Activate the dev container virtual environment before running backend tests directly:

```bash
source .venv/bin/activate
PYTHONPATH=backend/src python3 -m unittest discover backend/tests
```

Build the portal directly:

```bash
cd frontend
npm run build
```

When running the portal outside Compose but still using Vite dev server, the API proxy defaults to `http://127.0.0.1:8000`. Override it if your backend is somewhere else:

```bash
cd frontend
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --host 0.0.0.0 --port 5173
```

## Notes

- The devcontainer intentionally avoids the `docker-outside-of-docker` feature because the universal Codespaces image already provides Docker tooling and the extra feature can fail during upstream apt repository key rotations.
- The default Compose stack is the recommended Codespaces path for routine development.
- The full profile is a lab scaffold and can be memory-intensive.
- Codespaces forwarded URLs are public/private according to your Codespaces port visibility settings; keep development credentials out of production use.
