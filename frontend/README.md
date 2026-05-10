# FizRMM Frontend

The frontend is a Vite React technician portal shell for the current FizRMM prototype.

For full project setup, see [../docs/INSTALL.md](../docs/INSTALL.md). The recommended local path is Docker:

```bash
docker compose up --build portal
```

The Compose portal service mounts `./frontend` into the container and keeps `node_modules` in the named `frontend_node_modules` volume. This keeps the Docker image small and avoids exporting the dependency tree into the image layer during full-profile builds. The first portal start installs dependencies into that volume with `npm ci`.

## Install

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
