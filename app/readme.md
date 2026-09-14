# Project Overview

This repository contains a full-stack application (backend + frontend) with container orchestration and local development helpers.

Paths referenced in this README are relative to the repository root.

**Contents:**
- **Backend:** `app/backend` (Python project; see `app/backend/pyproject.toml`)
- **Frontend:** `app/frontend` (Node/React/TS project; see `app/frontend/package.json`)
- **Containers:** `app/docker-compose.yml` and `app/Dockerfile`
- **Docs:** `app/docs`

**Goal of this README:** Provide a clear, step-by-step guide to get the project running locally, how the code is organized, how to run tests, and a small helper script to automate setup.

---

## Prerequisites

- Install Docker and Docker Compose (or Docker with the `docker compose` plugin).
- Install Node.js (LTS) and `npm` or `pnpm` for the frontend.
- Install Python 3.8+ and `pip` for the backend.
- Optional: `poetry` if you prefer using it for Python dependency management.

Verify basic commands work:

```bash
docker --version
docker compose version  # or: docker-compose --version
node --version
npm --version
python3 --version
```

---

## Quick automated setup (recommended)

A helper script `setup.sh` (in project root) performs typical setup tasks:

- Installs backend dependencies (using `poetry` if available, otherwise creates a Python venv and uses `pip install .`).
- Installs frontend dependencies with `npm install`.
- Builds and starts services via Docker Compose.

Run the script from the repository root:

```bash
./setup.sh
```

If you prefer to avoid starting containers, run only the dependency setup steps (see manual setup below).

---

## Manual setup (step-by-step)

1) Backend

 - Change directory to the backend:

```bash
cd app/backend
```

 - If you use `poetry`:

```bash
poetry install
```

 - Otherwise create a virtual environment and install with `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install .
```

 - Environment variables: create an `.env` file or export variables required by the backend (examples are usually documented near `app/backend/README.md` or in source config).

2) Frontend

```bash
cd app/frontend
npm install
npm run dev      # or `npm run start` depending on the project scripts
```

3) Containers (optional but recommended for services like databases)

From the repository root, start containers:

```bash
cd app
docker compose up -d --build    # or: docker-compose up -d --build
```

The helper `setup.sh` will attempt the correct compose command automatically.

---

## Running the application

- Backend typical URL: `http://localhost:8000` (adjust if your app uses a different port)
- Frontend typical URL: `http://localhost:3000`

Check container logs with:

```bash
docker compose logs -f    # or: docker-compose logs -f
```

Stop containers:

```bash
docker compose down
```

---

## Tests

Backend tests are under `app/tests`. Run them using the test runner configured in the backend (pytest is common):

```bash
cd app/backend
source .venv/bin/activate   # if you created a venv
pytest -q
```

Frontend tests (if present) run via npm scripts:

```bash
cd app/frontend
npm test
```

---

## Project structure (detailed)

```text
app/
├── backend/         # Python package; services, controllers, models, tests
│   ├── pyproject.toml
│   ├── app/         # application package
│   │   ├── api/
│   │   ├── controllers/
│   │   ├── services/
│   │   └── tests/
│   └── tests/
├── frontend/        # Node/React/TypeScript app
├── docker/          # helper docker resources (per-service folders)
├── docs/            # project documentation
├── docker-compose.yml
└── readme.md
```

Key locations:
- `app/backend/app` : backend source code and modules
- `app/frontend`    : frontend source and build config
- `app/docker`      : containers and DB init scripts

---

## Troubleshooting

- If `docker compose` is not available, try `docker-compose` (older CLI).
- If backend install fails with PEP517/pyproject errors, ensure `pip` is up-to-date: `python3 -m pip install -U pip build` then `pip install .`.
- File permissions: make `setup.sh` executable: `chmod +x setup.sh`.

---

## Contributing

- Fork and create feature branches.
- Follow the repository's linting and testing conventions.

---

---

## Helper script (embedded)

Below is a self-contained setup script you can copy into a file named `setup.sh` at the repository root. It automates backend/frontend dependency installation and can start Docker Compose. Save it, make it executable with `chmod +x setup.sh`, and run `./setup.sh`.

```bash
#!/usr/bin/env bash

# setup.sh - Project setup helper
# Usage: ./setup.sh [--no-docker] [--no-frontend] [--no-backend]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT_DIR/app"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"

SKIP_DOCKER=0
SKIP_FRONTEND=0
SKIP_BACKEND=0

for arg in "$@"; do
	case "$arg" in
		--no-docker) SKIP_DOCKER=1 ;;
		--no-frontend) SKIP_FRONTEND=1 ;;
		--no-backend) SKIP_BACKEND=1 ;;
		-h|--help)
			echo "Usage: $0 [--no-docker] [--no-frontend] [--no-backend]"
			exit 0
			;;
		*) echo "Unknown argument: $arg"; exit 2 ;;
	esac
done

check_cmd() {
	command -v "$1" >/dev/null 2>&1 || { echo "Required command '$1' not found. Please install it and retry."; exit 1; }
}

install_backend() {
	if [ "$SKIP_BACKEND" -eq 1 ]; then
		echo "Skipping backend setup."; return
	fi
	echo "Setting up backend in $BACKEND_DIR"
	if [ ! -d "$BACKEND_DIR" ]; then
		echo "Backend directory not found: $BACKEND_DIR"; return
	fi

	pushd "$BACKEND_DIR" >/dev/null

	if [ -f "pyproject.toml" ]; then
		if command -v poetry >/dev/null 2>&1; then
			echo "Installing backend dependencies with poetry..."
			poetry install
		else
			echo "No poetry detected. Creating venv and installing with pip..."
			python3 -m venv .venv
			. .venv/bin/activate
			pip install -U pip build
			pip install .
		fi
	elif [ -f "requirements.txt" ]; then
		echo "Creating venv and installing requirements.txt..."
		python3 -m venv .venv
		. .venv/bin/activate
		pip install -U pip
		pip install -r requirements.txt
	else
		echo "No pyproject.toml or requirements.txt found — skipping backend install."
	fi

	popd >/dev/null
}

install_frontend() {
	if [ "$SKIP_FRONTEND" -eq 1 ]; then
		echo "Skipping frontend setup."; return
	fi
	echo "Setting up frontend in $FRONTEND_DIR"
	if [ ! -d "$FRONTEND_DIR" ]; then
		echo "Frontend directory not found: $FRONTEND_DIR"; return
	fi
	pushd "$FRONTEND_DIR" >/dev/null
	if [ -f "package.json" ]; then
		if command -v npm >/dev/null 2>&1; then
			npm install
		else
			echo "npm not found — please install Node.js and npm to setup the frontend."; popd >/dev/null; return
		fi
	else
		echo "No package.json found in frontend — skipping frontend install."
	fi
	popd >/dev/null
}

start_docker() {
	if [ "$SKIP_DOCKER" -eq 1 ]; then
		echo "Skipping docker compose up."; return
	fi
	echo "Starting Docker Compose from $APP_DIR"
	pushd "$APP_DIR" >/dev/null
	if command -v docker >/dev/null 2>&1; then
		if docker compose version >/dev/null 2>&1; then
			docker compose up -d --build
		elif command -v docker-compose >/dev/null 2>&1; then
			docker-compose up -d --build
		else
			echo "docker compose plugin not found and docker-compose not found. Please install one."; popd >/dev/null; exit 1
		fi
	else
		echo "Docker not found. Please install Docker to run services."; popd >/dev/null; exit 1
	fi
	popd >/dev/null
}

main() {
	echo "Project setup started from: $ROOT_DIR"

	# Basic checks
	check_cmd python3 || true

	# Backend
	install_backend

	# Frontend
	install_frontend

	# Docker / containers
	start_docker

	echo "Setup complete."
	echo "Backend: http://localhost:8000 (if running)"
	echo "Frontend: http://localhost:3000 (if running)"
}

main
```

You told me not to keep the file in the repo — this embedded block lets you copy the script when you need it.

If you want, I can paste this script into a new `setup.sh` file again or further adapt it to your preferred package managers.

Thank you — tell me which of the options above you want next.
