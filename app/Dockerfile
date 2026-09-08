FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt* ./
COPY backend/pyproject.toml ./
COPY backend/README.md ./
COPY backend/app ./app

RUN python -m pip install --upgrade pip && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi && \
    if [ -f pyproject.toml ]; then pip install .; fi

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
