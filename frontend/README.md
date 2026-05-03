# FizRMM Frontend

The frontend is a Vite React technician portal shell for the current FizRMM prototype.

For full project setup, see [../docs/INSTALL.md](../docs/INSTALL.md). The recommended local path is Docker:

```bash
docker compose up --build portal
```

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

By default, the portal calls `http://127.0.0.1:8000`.

Override it with:

```bash
VITE_FIZRMM_API_BASE=http://127.0.0.1:8001 npm run dev -- --port 5173
```
