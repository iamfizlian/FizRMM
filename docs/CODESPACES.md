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

- `5173` for the FizRMM portal.
- `8000` for the FizRMM API.
- `5432` for PostgreSQL, if you need direct database access.

The portal should be available through the Codespaces forwarded URL for port `5173`; the API health endpoint should be available through the forwarded URL for port `8000`.

## Run the full lab scaffold

The full profile is heavier and may need a larger Codespaces machine size because it starts Keycloak, NATS, MeshCentral, Salt, Zabbix, Wazuh, and OpenSearch in addition to the app:

```bash
docker compose --profile full up --build
```

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

## Notes

- The devcontainer intentionally avoids the `docker-outside-of-docker` feature because the universal Codespaces image already provides Docker tooling and the extra feature can fail during upstream apt repository key rotations.
- The default Compose stack is the recommended Codespaces path for routine development.
- The full profile is a lab scaffold and can be memory-intensive.
- Codespaces forwarded URLs are public/private according to your Codespaces port visibility settings; keep development credentials out of production use.
