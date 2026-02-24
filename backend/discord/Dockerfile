FROM ghcr.io/astral-sh/uv:0.10.5-python3.11-trixie-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

FROM python:3.11.11-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY shared/ ./shared/
COPY discord/ ./discord/
COPY data/ ./data/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

WORKDIR /app/discord
EXPOSE 8080
CMD ["python", "bot.py"]
