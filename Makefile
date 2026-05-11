.PHONY: backend test-backend frontend frontend-build install start up docker-up stop docker-down restart update integrations integrations-build integrations-pull docker-prune

backend:
	PYTHONPATH=backend/src python3 -m fizrmm

test-backend:
	PYTHONPATH=backend/src python3 -m unittest discover backend/tests

frontend:
	cd frontend && npm run dev

frontend-build:
	docker compose build portal
	docker compose run --rm --no-deps portal sh -c 'if [ ! -d node_modules/vite ] || [ ! -d node_modules/react ]; then npm ci; fi; npm run build'

install start up docker-up:
	./fizrmm start

stop docker-down:
	./fizrmm stop

restart:
	./fizrmm restart

update:
	./fizrmm

integrations-pull:
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile integrations pull

integrations-build:
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile integrations build api
	COMPOSE_PARALLEL_LIMIT=1 docker compose --profile integrations build portal

integrations:
	./fizrmm integrations

docker-prune:
	docker builder prune -f
	docker image prune -f
