FROM python:3.11-slim
WORKDIR /app

# Optional: set at build time for /version (e.g. docker build --build-arg GIT_SHA=$(git rev-parse --short HEAD))
ARG GIT_SHA=unknown
ENV EDON_GIT_SHA=${GIT_SHA}
ENV GIT_SHA=${GIT_SHA}

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.gateway.txt ./requirements.gateway.txt
RUN pip install --no-cache-dir -r requirements.gateway.txt

COPY edon_gateway/ ./edon_gateway/
ENV PYTHONPATH=/app

# Persisted data (mount volume at /app/data)
RUN mkdir -p /app/data

EXPOSE 8080

# Fly sets PORT=8080; use it so we always match fly-proxy
ENV PORT=8080
ENV ENVIRONMENT=production
ENV EDON_ENV=production
# Set to true only during initial bootstrap; flip to false for production lock-down
ENV EDON_ALLOW_ENV_TOKEN_IN_PROD=false
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf "http://localhost:${PORT}/health" || exit 1

# Run uvicorn; EDON_WORKERS defaults to 1 (override via fly.toml env for multi-worker deployments).
CMD ["sh", "-c", "exec python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${EDON_WORKERS:-1}"]
