# syntax=docker/dockerfile:1.7
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 CODECORTEX_BACKEND_HOME=/opt/codecortex/backends CODECORTEX_BACKENDS=builtin
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential ca-certificates && rm -rf /var/lib/apt/lists/* && python -m pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

FROM base AS core
RUN useradd --create-home --uid 10001 cortex && mkdir -p /workspace /opt/codecortex/backends && chown -R cortex:cortex /workspace /opt/codecortex/backends
USER cortex
WORKDIR /workspace
ENTRYPOINT ["cortex"]
CMD ["--help"]

FROM base AS full
RUN python -m pip install --no-cache-dir ".[semantic,parsers]" && useradd --create-home --uid 10001 cortex && mkdir -p /workspace /opt/codecortex/backends && chown -R cortex:cortex /workspace /opt/codecortex/backends
USER cortex
WORKDIR /workspace
ENTRYPOINT ["cortex"]
CMD ["--help"]

FROM base AS api
RUN python -m pip install --no-cache-dir ".[web,parsers]" && useradd --create-home --uid 10001 cortex && mkdir -p /workspace /var/lib/codecortex /opt/codecortex/backends && chown -R cortex:cortex /workspace /var/lib/codecortex /opt/codecortex/backends
USER cortex
WORKDIR /workspace
EXPOSE 7340
ENTRYPOINT ["cortex-api"]
CMD ["--host", "0.0.0.0", "--port", "7340", "--state-dir", "/var/lib/codecortex"]

FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json ./
RUN npm install
COPY web ./
RUN npm run build

FROM nginx:1.27-alpine AS console
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
