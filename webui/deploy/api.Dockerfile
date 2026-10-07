# Web-UI Backend (FastAPI) und Hintergrunddienst (worker) in einem Image. Basis-Images per Digest gepinnt.
# Enthält das Framework (tools/, config/, Regeln, Vorlagen, Doku) unter /app/framework und die
# Claude Code CLI. Spielstand und App-Konfiguration liegen nur in Volumes (/data, /data-app).
ARG REGISTRY=docker.io/library

# Claude Code CLI über npm in einem eigenen Schritt; ins Laufzeit-Image kommt nur das Programm.
FROM ${REGISTRY}/node:22-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS claude
# Version bewusst fest: Modell- und Aufwandsoptionen in config/claude.json sind gegen sie geprüft.
ARG CLAUDE_CODE_VERSION=2.1.292
RUN npm install --global --omit=dev --no-fund --no-audit "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
 && /usr/local/bin/claude --version

FROM ${REGISTRY}/python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

ARG SM_VERSION=entwicklung
ENV SM_VERSION=${SM_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:/usr/local/bin:$PATH \
    STOCKMASTER_FRAMEWORK_DIR=/app/framework \
    STOCKMASTER_DATA_DIR=/data \
    STOCKMASTER_APP_DIR=/data-app \
    DISABLE_AUTOUPDATER=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "uv==0.11.32" \
 && git config --system --add safe.directory /data \
 && git config --system init.defaultBranch main

# Das npm-Paket installiert ein eigenständiges Programm (bin/claude.exe); Node.js ist zur Laufzeit nicht nötig.
COPY --from=claude /usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe /usr/local/bin/claude
RUN claude --version

WORKDIR /app
COPY webui/backend/pyproject.toml webui/backend/uv.lock webui/backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY webui/backend/stockmaster ./stockmaster
COPY webui/backend/alembic ./alembic
COPY webui/backend/alembic.ini ./

# Framework: nur lesend im Image (Code, Regeln, Konfiguration, Vorlagen, Doku), nie Spielstand.
COPY tools /app/framework/tools
COPY config /app/framework/config
COPY vorlagen /app/framework/vorlagen
COPY regeln.md CLAUDE.md STATUS.md KONZEPT.md README.md AUFTRAG_PHASE1.md AUFTRAG_WEBUI.md requirements.txt /app/framework/

# Volumes: leere Mountpunkte, die dem Laufzeitbenutzer gehören (neue benannte Volumes übernehmen das).
RUN useradd --system --uid 10001 --no-create-home --home-dir /tmp stockmaster \
 && mkdir -p /data /data-app /geheim \
 && chown 10001:10001 /data /data-app \
 && chmod 0700 /data-app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
# vorbereiten: Datenbank, leeres Datenverzeichnis aus der Vorlage, Master-Schlüssel, Übernahme alter Variablen.
CMD ["sh", "-c", "python -m stockmaster vorbereiten && exec uvicorn stockmaster.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
