# Prepare the base environment.
FROM python:3.7.2-slim-stretch as builder_base_caddy
MAINTAINER asi@dbca.wa.gov.au
RUN apt-get update -y \
  && apt-get install -y wget gcc binutils libproj-dev gdal-bin \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --upgrade pip

# Install Python libs from requirements.txt.
FROM builder_base_caddy as python_libs_caddy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the project.
COPY geocoder.py gunicorn.ini manage.py ./
COPY caddy ./caddy
COPY shack ./shack
EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.ini"]
