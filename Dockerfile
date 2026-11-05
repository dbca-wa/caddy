# syntax=docker/dockerfile:1
# Args to centralise versions.
# PYTHON_VERSION is the DHI runtime tag.
ARG PYTHON_VERSION=3.13-debian13-dev
ARG UV_VERSION=0.13

# ---- Stages ----
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM dhi.io/python:${PYTHON_VERSION} AS builder

# ---- Builder stage ----
# gcc is required: gunicorn[fast] -> gunicorn-h1c has no wheel for every
# platform and builds its extension from source.
COPY --from=uv /uv /bin/uv

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update && apt-get install -y --no-install-recommends gcc

# Install only runtime dependencies into /app/.venv. The venv path must match
# the runtime stage: uv writes absolute shebangs into console scripts such as
# gunicorn.
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  uv sync --locked --no-group dev --link-mode=copy --compile-bytecode --no-python-downloads

# ---- Runtime stage ----
FROM dhi.io/python:${PYTHON_VERSION} AS runtime
LABEL org.opencontainers.image.title="caddy" \
  org.opencontainers.image.description="DBCA Cadastre Indexer" \
  org.opencontainers.image.source="https://github.com/dbca-wa/caddy" \
  org.opencontainers.image.vendor="DBCA" \
  org.opencontainers.image.authors="asi@dbca.wa.gov.au"

# Environment variables
ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PATH="/app/.venv/bin:$PATH"

# GDAL/GEOS/PROJ runtime libraries for django.contrib.gis. The DHI base has no
# /etc/ld.so.cache, so ldconfig is required for Django's ctypes-based lookup.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update && apt-get install -y --no-install-recommends \
  libgdal36 \
  libgeos-c1t64 \
  libproj25 \
  proj-data \
  && ldconfig

# Copy installed virtualenv from builder (same path, so console-script shebangs stay valid).
WORKDIR /app
COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv

# Copy the application files
COPY --chown=nonroot:nonroot gunicorn.py manage.py ./
COPY --chown=nonroot:nonroot caddy ./caddy
COPY --chown=nonroot:nonroot shack ./shack

RUN <<EOF
python -m compileall -q manage.py caddy shack
python manage.py collectstatic --noinput
EOF

# Image runs as the nonroot user
USER nonroot
EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.py"]
