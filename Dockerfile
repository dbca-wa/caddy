# syntax=docker/dockerfile:1
# Prepare the base environment.
FROM python:3.11.8-slim as builder_base_caddy
MAINTAINER asi@dbca.wa.gov.au
LABEL org.opencontainers.image.source https://github.com/dbca-wa/caddy

RUN apt-get update -y \
  && apt-get upgrade -y \
  && apt-get install -y libmagic-dev gcc binutils gdal-bin proj-bin python3-dev libpq-dev \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --upgrade pip

# Install Python libs using poetry.
FROM builder_base_caddy as python_libs_caddy
WORKDIR /app
ENV POETRY_VERSION=1.7.1
RUN pip install poetry=="${POETRY_VERSION}"
COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --only main

# Create a non-root user.
ARG UID=10001
ARG GID=10001
RUN groupadd -g "${GID}" appuser \
  && useradd --no-create-home --no-log-init --uid "${UID}" --gid "${GID}" appuser

# Install the project.
COPY geocoder.py gunicorn.py manage.py ./
COPY caddy ./caddy
COPY shack ./shack

USER ${UID}
EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.py"]
