# GitHub Codespaces

FizRMM can run in a GitHub Codespace for development and demos. The default Codespaces workflow starts the application only: PostgreSQL, API, and portal.

## Start a Codespace

1. Open the repository in GitHub.
2. Select **Code** → **Codespaces** → **Create codespace on current branch**.
3. Wait for the dev container `postCreateCommand` to finish.

## Run FizRMM

From the Codespaces terminal:

```bash
./fizrmm
```

Open the forwarded ports panel and use:

- `5173` for the FizRMM portal.
- `8000` for the API, only if you want to inspect API responses directly.
- `5432` for PostgreSQL, only if you need direct database access.

Run the same command again after updates are available; it pulls, rebuilds, and restarts the app:

```bash
./fizrmm
```

The portal should be available through the Codespaces forwarded URL for port `5173`. Browser API requests use the same forwarded `5173` origin because the portal proxies `/api` to the API container.

Current UI workflows:

- Select assets.
- Create endpoint enrollment tokens and download Windows/Linux bootstrap scripts.
- Queue automation/script requests against selected assets.
- Inspect integration readiness, alerts, and timeline-derived logs.
- Use **Access** as platform admin to create organizations.

## Optional Integration Containers

Optional Keycloak, MeshCentral, Zabbix, Wazuh, Salt, NATS, OpenSearch, and `fizrmm-init` containers are not started by default. Only run them when developing integration adapters:

```bash
./fizrmm integrations
```

Additional forwarded ports for that optional profile:

- `8443` for MeshCentral.
- `8081` for Zabbix Web.
- `8080` for Keycloak.

## Run tests

Backend tests can be run through Make from either the repository root or `frontend/`:

```bash
make test-backend
```

If you want to invoke Python directly from the repository root, activate the dev container virtual environment first:

```bash
source .venv/bin/activate
PYTHONPATH=backend/src python3 -m unittest discover backend/tests
```

Build the portal through Docker when your host does not have Node.js/npm installed:

```bash
make frontend-build
```

Because the devcontainer installs frontend dependencies, you can also build directly inside Codespaces:

```bash
cd frontend
npm run build
```

If your shell is already in `frontend/`, run only:

```bash
npm run build
```

## Troubleshooting

If PostgreSQL exits with a `/var/lib/postgresql/data` volume-layout error, reset development volumes and start again:

```bash
docker compose down --volumes --remove-orphans
./fizrmm
```

If Docker reports `no space left on device`, run:

```bash
make docker-prune
```

For Codespaces that have accumulated many large images or volumes, you may need to remove unused volumes after saving any data you need.

## Notes

- The devcontainer intentionally avoids the `docker-outside-of-docker` feature because the universal Codespaces image already provides Docker tooling.
- The optional integration containers are memory-intensive; the default application stack is the recommended Codespaces path.
- Codespaces forwarded URLs are public/private according to your Codespaces port visibility settings.
