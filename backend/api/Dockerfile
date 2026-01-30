# Stage 1: Build
FROM ghcr.io/astral-sh/uv:0.5.21 AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

# Stage 2: Run
FROM python:3.11.10-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

# 只複製 API 相關與通用程式碼
COPY api/ ./api/
COPY main.py .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 4344
CMD ["python", "main.py"]