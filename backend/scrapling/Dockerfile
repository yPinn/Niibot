FROM python:3.12.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv
ENV UV_LINK_MODE=copy \
    UV_NATIVE_TLS=1
WORKDIR /app
COPY scrapling/pyproject.toml scrapling/uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project --no-dev

FROM python:3.12.12-slim-bookworm
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=3001
RUN playwright install chromium --with-deps
COPY scrapling/main.py scrapling/stealth.js ./
COPY shared/discord_webhook_handler.py ./
EXPOSE 3001
CMD ["python", "main.py"]
