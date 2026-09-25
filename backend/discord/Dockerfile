FROM python:3.12.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv
ENV UV_LINK_MODE=copy \
    UV_SYSTEM_CERTS=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project --no-dev

FROM python:3.12.12-slim-bookworm
# hadolint ignore=DL3008,DL3009
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    fonts-noto-core \
    curl \
    && curl -fsSL \
       -o /usr/share/fonts/truetype/noto/NotoSansCanadianAboriginal-Regular.ttf \
       "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansCanadianAboriginal/NotoSansCanadianAboriginal-Regular.ttf" \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*
ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.version=$APP_VERSION \
    org.opencontainers.image.source="https://github.com/yPinn/Niibot"
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY shared/ ./shared/
COPY discord/ ./discord/
COPY scripts/ ./scripts/
COPY data/ ./data/
RUN mkdir -p /app/runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=$APP_VERSION \
    GIT_COMMIT=$GIT_COMMIT

WORKDIR /app/discord
EXPOSE 8080
CMD ["python", "bot.py"]
