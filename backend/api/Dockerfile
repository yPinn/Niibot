# Stage 1: Build
FROM ghcr.io/astral-sh/uv:0.5.21-python3.11-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

# Stage 2: Run
FROM python:3.11.10-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

# 複製 API 相關程式碼
COPY api/ ./api/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/api
EXPOSE 4344
CMD ["python", "main.py"]