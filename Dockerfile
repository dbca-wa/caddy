# syntax=docker/dockerfile:1
# Prepare the base environment.
FROM python:3.12.6-alpine AS builder_base
LABEL org.opencontainers.image.authors=asi@dbca.wa.gov.au
LABEL org.opencontainers.image.source=https://github.com/dbca-wa/caddy

# Install system requirements to build Python packages.
RUN apk add --no-cache \
  gcc \
  libressl-dev \
  musl-dev \
  libffi-dev
# Create a non-root user to run the application.
ARG UID=10001
ARG GID=10001
RUN addgroup -g ${GID} appuser \
  && adduser -H -D -u ${UID} -G appuser appuser

# Install Python libs using Poetry.
FROM builder_base AS python_libs_caddy
# Add system dependencies required to use GDAL
RUN apk add --no-cache \
  gdal \
  geos \
  proj \
  binutils
WORKDIR /app
COPY poetry.lock pyproject.toml ./
ARG POETRY_VERSION=1.8.3
RUN pip install --no-cache-dir --root-user-action=ignore poetry==${POETRY_VERSION} \
  && poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --only main
# Remove system libraries, no longer required.
RUN apk del \
  gcc \
  libressl-dev \
  musl-dev \
  libffi-dev

# Install the project.
FROM python_libs_caddy AS project_caddy
COPY geocoder.py gunicorn.py manage.py ./
COPY caddy ./caddy
COPY shack ./shack
USER ${UID}
EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.py"]
