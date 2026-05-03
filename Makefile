.PHONY: backend test-backend frontend docker-up docker-down infra

backend:
	PYTHONPATH=backend/src python3 -m fizrmm

test-backend:
	PYTHONPATH=backend/src python3 -m unittest discover backend/tests

frontend:
	cd frontend && npm run dev

docker-up:
	docker compose up --build

docker-down:
	docker compose down

infra:
	docker compose --profile infra up -d postgres keycloak nats opensearch
