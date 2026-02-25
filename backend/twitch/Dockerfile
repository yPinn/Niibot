FROM ghcr.io/astral-sh/uv:0.10.5-python3.11-bookworm-slim AS builder
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project --no-dev

FROM python:3.11.11-slim
ARG APP_VERSION=dev
LABEL org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.source="https://github.com/yPinn/Niibot"
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY shared/ ./shared/
COPY twitch/ ./twitch/
COPY data/ ./data/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

WORKDIR /app/twitch
EXPOSE 4344
CMD ["python", "main.py"]
