SHELL := /bin/bash

.PHONY: help install install-frontend install-backend check check-frontend check-backend \
	docker-config deploy d update u restart r logs l status ps stop down infra-up infra-down \
	migrate seed test test-backend

help:
	@printf "\nAI Novel 快捷命令\n"
	@printf "  make infra-up                启动 postgres / redis / temporal / minio\n"
	@printf "  make migrate                 执行 alembic upgrade head\n"
	@printf "  make seed                    注入种子数据（plans / admin / demo project）\n"
	@printf "  make test                    运行后端 pytest\n"
	@printf "  make deploy   / make d       一键构建并启动全套服务\n"
	@printf "  make update   / make u       拉取最新代码并重建服务\n"
	@printf "  make logs     / make l       查看服务日志\n"
	@printf "  make status   / make s       查看服务状态\n"
	@printf "  make restart  / make r       重启前后端服务\n"
	@printf "  make down                    停止全部服务\n"
	@printf "  make check                   前后端基础校验\n\n"

install: install-frontend install-backend

install-frontend:
	cd frontend && npm install

check-frontend:
	cd frontend && npm run lint && npm run typecheck && npm run build

install-backend:
	cd backend && python -m pip install --upgrade pip && python -m pip install -e '.[dev]'

check-backend:
	cd backend && python -m compileall app

check: check-frontend check-backend docker-config

docker-config:
	docker compose config >/dev/null

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && python -m app.repositories.seed

test test-backend:
	cd backend && pytest -v -m "not postgres"

test-postgres:
	cd backend && pytest -v -m postgres

worker:
	cd backend && python -m app.workers.main

deploy:
	./scripts/deploy.sh

d: deploy

update:
	./scripts/update.sh

u: update

restart:
	docker compose restart backend frontend

r: restart

logs:
	docker compose logs -f --tail=200

l: logs

status:
	docker compose ps

ps: status

stop down:
	docker compose down

infra-up:
	docker compose up -d postgres redis temporal-postgres temporal temporal-ui minio

infra-down:
	docker compose down
