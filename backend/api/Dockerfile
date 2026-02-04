FROM ghcr.io/astral-sh/uv:0.5.21-python3.11-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

FROM python:3.11.10-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY shared/ ./shared/
COPY api/ ./api/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/api
EXPOSE 8000
CMD ["python", "main.py"]
