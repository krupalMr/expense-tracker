PYTHON ?= python3
VENV := backend/.venv
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

.PHONY: install backend frontend start build clean

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -r backend/requirements.txt
	npm --prefix frontend install

backend:
	$(UVICORN) --app-dir backend app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	npm --prefix frontend run dev

start: install
	@trap 'kill 0' INT TERM EXIT; \
	$(UVICORN) --app-dir backend app.main:app --reload --host 0.0.0.0 --port 8000 & \
	npm --prefix frontend run dev & \
	wait

build:
	npm --prefix frontend run build

clean:
	rm -rf frontend/dist frontend/node_modules backend/.venv
