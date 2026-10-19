# Образ бота. С моделью: docker build --build-arg EXTRAS="--extra ml" .
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libfribidi0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /bin/uv

WORKDIR /app
ARG EXTRAS=""
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project $EXTRAS
COPY src ./src
COPY curriculum ./curriculum
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev $EXTRAS

# Непривилегированный пользователь (docs/security/threat-model.md)
RUN useradd --system --uid 10001 --home /app muallim \
    && mkdir -p /app/data/audio /app/data/erasures && chown -R muallim /app/data
USER muallim
ENV PATH="/app/.venv/bin:$PATH"
# Миграции — не при старте: бот входит ролью muallim_app без прав на схему; их применяет человек
# командой make migrate (сначала копия БД), ADR-0054, TD-DB-03.
CMD ["muallim"]
