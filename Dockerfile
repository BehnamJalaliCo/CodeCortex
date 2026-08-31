# syntax=docker/dockerfile:1.7
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CODECORTEX_BACKEND_HOME=/opt/codecortex/backends \
    CODECORTEX_BACKENDS=builtin

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

FROM base AS core
RUN useradd --create-home --uid 10001 cortex \
    && mkdir -p /workspace /opt/codecortex/backends \
    && chown -R cortex:cortex /workspace /opt/codecortex/backends
USER cortex
WORKDIR /workspace
ENTRYPOINT ["cortex"]
CMD ["--help"]

FROM base AS full
RUN python -m pip install --no-cache-dir ".[semantic,parsers]" \
    && useradd --create-home --uid 10001 cortex \
    && mkdir -p /workspace /opt/codecortex/backends \
    && chown -R cortex:cortex /workspace /opt/codecortex/backends
USER cortex
WORKDIR /workspace
ENTRYPOINT ["cortex"]
CMD ["--help"]
