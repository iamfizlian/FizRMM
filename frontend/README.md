# FizRMM Frontend

The frontend is a Vite React technician portal shell for the current FizRMM prototype.

For full project setup, see [../docs/INSTALL.md](../docs/INSTALL.md). The recommended Docker install/start path is a single Make target from the repository root or this `frontend/` directory:

```bash
make start
```

Stop it with:

```bash
make stop
```

The Compose portal service mounts `./frontend` into the container and keeps `node_modules` in the named `frontend_node_modules` volume. This keeps the Docker image small and avoids exporting the dependency tree into the image layer during full-profile builds. The first portal start installs dependencies into that volume with `npm ci`.

## Install

No host Node.js/npm install is required for the Docker workflow. Compose installs dependencies into the `frontend_node_modules` volume the first time the portal container starts.

Manual frontend install, without Docker:

```bash
npm install
```

## Run

Start the backend first from the repo root:

```bash
PYTHONPATH=backend/src python3 -m fizrmm
```

Then start the portal:

```bash
cd frontend
npm run dev -- --port 5173
```

Open `http://127.0.0.1:5173/`.

## Build

Use the Docker-backed build if your host does not have npm installed. This works from the repository root or from `frontend/`:

```bash
make frontend-build
```

The frontend Makefile also delegates backend and stack helpers to the repository root, so `make test-backend`, `make start`, `make stop`, `make restart`, `make full-build`, and `make full-pull` work from this directory.

Or build directly when npm is available locally:

```bash
npm run build
```

## API URL

By default, the portal calls same-origin `/api` routes. In development, Vite proxies those API requests to `http://127.0.0.1:8000`. Docker Compose overrides the proxy target to `http://api:8000` so Codespaces and remote browser sessions work through the forwarded portal URL.

Override the Vite proxy target for local development with:

```bash
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5173
```

If you need the browser to call a fully separate API origin directly, set `VITE_FIZRMM_API_BASE`:

```bash
VITE_FIZRMM_API_BASE=https://api.example.test npm run dev -- --port 5173
```
