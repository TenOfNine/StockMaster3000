# Web-UI Backend (FastAPI). Basis-Images per Digest gepinnt.
ARG REGISTRY=docker.io/library
FROM ${REGISTRY}/python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    SM_REPO_PFAD=/repo

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "uv==0.11.32" \
 && git config --system --add safe.directory /repo

WORKDIR /app
COPY webui/backend/pyproject.toml webui/backend/uv.lock webui/backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY webui/backend/stockmaster ./stockmaster
COPY webui/backend/alembic ./alembic
COPY webui/backend/alembic.ini ./

RUN useradd --system --uid 10001 --no-create-home stockmaster
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["sh", "-c", "python -m stockmaster migrieren && exec uvicorn stockmaster.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
