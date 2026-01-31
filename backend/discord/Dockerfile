# Stage 1: Build
FROM ghcr.io/astral-sh/uv:0.5.21-python3.11-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

# Stage 2: Run
FROM python:3.11.10-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

# 依照你的結構：Discord 相關檔案在根目錄與資料夾
COPY discord/ ./discord/
COPY data/ ./data/
COPY discord/bot.py .

RUN mkdir -p /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "bot.py"]