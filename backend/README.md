# FizRMM Backend

The backend exposes the current FizRMM control-plane API. Under Docker it uses PostgreSQL through `DATABASE_URL`; without `DATABASE_URL`, it falls back to an in-memory store for quick local tests.

For full project setup, see [../docs/INSTALL.md](../docs/INSTALL.md). The recommended local path is Docker:

```bash
docker compose up --build api
```

## Install

Manual backend install, without Docker:

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

## Run

```bash
PYTHONPATH=backend/src python3 -m fizrmm
```

The API listens on `http://127.0.0.1:8000`.

## Test

```bash
PYTHONPATH=backend/src python3 -m unittest discover backend/tests
```

## API Contracts

- `GET /health`
- `GET /api/orgs`
- `GET /api/assets`
- `GET /api/assets/{asset_id}`
- `GET /api/assets/{asset_id}/agents`
- `GET /api/assets/{asset_id}/timeline`
- `GET /api/scripts`
- `POST /api/assets/{asset_id}/remote-sessions`
- `POST /api/assets/{asset_id}/script-runs`

## Tenant Simulation

Tenant context is simulated through headers:

- `X-FizRMM-User`: technician identity, defaults to `demo-tech`
- `X-FizRMM-Orgs`: comma-separated allowed org IDs, defaults to `org_acme`
- `X-FizRMM-Role`: set to `platform-admin` for all-org access

Examples:

```bash
curl -H 'X-FizRMM-Orgs: org_acme' http://127.0.0.1:8000/api/assets
curl -H 'X-FizRMM-Role: platform-admin' http://127.0.0.1:8000/api/assets
```

This mirrors the intended Keycloak claim and PostgreSQL RLS model while the real identity provider and database are being wired in.
