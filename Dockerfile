# ── Dockerfile for Kristo Intelligence 6 ─────────────────────────────────────
# Multi-stage build: Python 3.12 slim + Node.js 20 (for market_evaluator.js)
# Optimized for production: non-root user, health check, minimal image size.

FROM python:3.12-slim AS base

# ── System dependencies ────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Create non-root user ───────────────────────────────────────────────────
RUN useradd --create-home --shell /bin/bash kristo
WORKDIR /app
RUN chown kristo:kristo /app

# ── Install Python dependencies ────────────────────────────────────────────
COPY --chown=kristo:kristo requirements.txt ./
USER kristo
RUN pip install --user --no-cache-dir --upgrade pip \
    && pip install --user --no-cache-dir -r requirements.txt

# ── Copy application code ──────────────────────────────────────────────────
USER root
COPY --chown=kristo:kristo . .
USER kristo

# ── Add user pip bin to PATH ───────────────────────────────────────────────
ENV PATH="/home/kristo/.local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=10000

# ── Health check (every 30s, allow 60s startup) ────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# ── Expose port ────────────────────────────────────────────────────────────
EXPOSE ${PORT}

# ── Run with gunicorn (1 worker + 8 threads for background threads) ────────
CMD ["sh", "-c", "gunicorn --bind=0.0.0.0:${PORT} --workers=1 --threads=8 --timeout=120 main:app"]
