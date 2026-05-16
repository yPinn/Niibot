FROM python:3.12.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY scrapling/requirements.txt ./
RUN uv venv && uv pip install --no-cache -r requirements.txt

FROM python:3.12.12-slim-bookworm
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
