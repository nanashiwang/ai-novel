.PHONY: install-frontend check-frontend install-backend check-backend infra-up infra-down

install-frontend:
	cd frontend && npm install

check-frontend:
	cd frontend && npm run lint && npm run typecheck && npm run build

install-backend:
	cd backend && python -m pip install --upgrade pip && python -m pip install -e '.[dev]'

check-backend:
	cd backend && python -m compileall app

infra-up:
	docker compose up -d

infra-down:
	docker compose down
