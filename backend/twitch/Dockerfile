# Stage 1: Build
FROM ghcr.io/astral-sh/uv:0.5.21 AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

# Stage 2: Run
FROM python:3.11.10-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

# 依照你的結構：Twitch 在資料夾內
COPY twitch/ ./twitch/
RUN mkdir -p /app/twitch /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "twitch.main"]