FROM astral-sh/uv:python3.11-alpine AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

COPY . .
RUN mkdir -p /app/data /app/twitch

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 4344

CMD ["python", "main.py"]