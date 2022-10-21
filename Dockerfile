# Prepare the base environment.
FROM python:3.9.15-slim-buster as builder_base
MAINTAINER asi@dbca.wa.gov.au
LABEL org.opencontainers.image.source https://github.com/dbca-wa/caddy

RUN apt-get update -y \
  && apt-get upgrade -y \
  && apt-get install -y libmagic-dev gcc binutils gdal-bin proj-bin python3-dev libpq-dev \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --upgrade pip

# Install Python libs using poetry.
FROM builder_base as python_libs
WORKDIR /app
ENV POETRY_VERSION=1.2.2
RUN pip install "poetry==$POETRY_VERSION"
COPY poetry.lock pyproject.toml /app/
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --only main

# Install the project.
COPY geocoder.py gunicorn.py manage.py ./
COPY caddy ./caddy
COPY cddp ./cddp
COPY shack ./shack

# Run the application as the www-data user.
USER www-data
EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.py"]
