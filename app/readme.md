# Project Overview

This repository contains a full-stack application with:

- Backend: Python service in `app/backend`
- Frontend: UI project in `app/frontend`
- Container setup: `docker-compose.yml` and `Dockerfile`
- Documentation: `docs/`

## Quick start

1. Start the containers:
   ```bash
   docker-compose up --build
   ```
2. Backend will be available at `http://localhost:8000`
3. Frontend will be available at `http://localhost:3000`

## Project structure

```text
app/
├── backend/
├── frontend/
├── docs/
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── readme.md
└── .venv/
```

## Notes

- Update the backend configuration and app entrypoint as the project grows.
- Keep environment variables in `.env` files or a secure secret manager for production.
