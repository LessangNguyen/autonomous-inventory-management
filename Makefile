# Developer shortcuts. Works with GNU Make (Linux/macOS/WSL/Git Bash).
# On native Windows PowerShell, run the underlying commands from README.md.

PY ?= python
VENV ?= .venv
API ?= http://127.0.0.1:8000

.PHONY: help venv install backend frontend build test lint seed clean docker-up docker-down

help:
	@echo "install      - create .venv and install backend + frontend dependencies"
	@echo "backend      - run the FastAPI dev server on :8000"
	@echo "frontend     - run the Vite dev server on :5173"
	@echo "build        - type-check and build the frontend bundle"
	@echo "test         - run the backend pytest suite"
	@echo "docker-up    - docker compose up --build (Postgres + API + UI)"
	@echo "docker-down  - stop the compose stack"
	@echo "clean        - remove local databases, caches and build output"

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(VENV)/Scripts/python -m pip install --upgrade pip || $(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/Scripts/python -m pip install -r backend/requirements.txt || $(VENV)/bin/python -m pip install -r backend/requirements.txt
	cd frontend && npm install

backend:
	cd backend && ../$(VENV)/Scripts/python -m uvicorn app.main:app --reload --port 8000 || cd backend && ../$(VENV)/bin/python -m uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

test:
	cd backend && ../$(VENV)/Scripts/python -m pytest -q || cd backend && ../$(VENV)/bin/python -m pytest -q

seed:
	@echo "Demo data is opt-in: set SEED_DEMO_DATA=true and restart on an empty database."

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf backend/inventory.db backend/test_inventory.db backend/.pytest_cache frontend/dist frontend/node_modules
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
