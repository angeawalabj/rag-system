# ─────────────────────────────────────────────────────────────────────────────
# Ingestion Service — Dockerfile multi-stage
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1 : dépendances ───────────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2 : production ────────────────────────────────────────────────────
FROM python:3.12-slim AS production

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /install /usr/local
COPY src/ ./src/

RUN mkdir -p /app/uploads

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "-m", "src.main"]

# ── Stage 3 : dev (hot-reload) ──────────────────────────────────────────────
FROM production AS development

COPY --from=deps /install /usr/local
RUN pip install --no-cache-dir watchfiles

CMD ["python", "-m", "watchfiles", "src.main:app", "--sigint-timeout", "5"]
