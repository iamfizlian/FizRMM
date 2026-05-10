.PHONY: backend test-backend frontend frontend-build docker-up docker-down infra full full-build full-pull docker-prune

backend:
	PYTHONPATH=backend/src python3 -m fizrmm

test-backend:
	PYTHONPATH=backend/src python3 -m unittest discover backend/tests

frontend:
	cd frontend && npm run dev

frontend-build:
	docker compose build portal
	docker compose run --rm --no-deps portal sh -c 'if [ ! -d node_modules/vite ] || [ ! -d node_modules/react ]; then npm ci; fi; npm run build'

docker-up:
	docker compose up --build

docker-down:
	docker compose down

infra:
	docker compose --profile infra up -d postgres keycloak nats opensearch

full-pull:
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full pull

full-build:
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full build api
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full build portal

full: full-build
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile full up --no-build

docker-prune:
	docker builder prune -f
	docker image prune -f
