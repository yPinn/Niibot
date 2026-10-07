FROM python:3.12.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv
ENV UV_LINK_MODE=copy \
    UV_SYSTEM_CERTS=1
WORKDIR /app
COPY scrapling/pyproject.toml scrapling/uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project --no-dev

FROM python:3.12.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=3001
# Static: Chromium and its system libraries change only with the playwright
# version (the venv above), so they sit below the daily security refresh and
# stay in the layer cache instead of being downloaded again every day.
RUN playwright install chromium --with-deps && rm -rf /var/lib/apt/lists/*
# The deploy passes the UTC date: a changed value rebuilds this layer, so the
# build host's layer cache can't pin an old Debian security patch level. It
# upgrades the system libraries Chromium installed above too.
ARG SECURITY_REFRESH=manual
RUN echo "security refresh: ${SECURITY_REFRESH}" \
    && apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY scrapling/main.py scrapling/stealth.js scrapling/browser_admission.py ./
COPY shared/discord_webhook_handler.py ./
EXPOSE 3001
CMD ["python", "main.py"]
