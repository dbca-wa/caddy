# Prepare the base environment.
FROM python:3.7-slim-buster as builder_base_caddy
MAINTAINER asi@dbca.wa.gov.au
RUN apt-get update -y \
  && apt-get upgrade -y \
  && apt-get install -y wget gcc binutils gdal-bin proj-bin \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --upgrade pip

# Install Python libs from requirements.txt.
FROM builder_base_caddy as python_libs_caddy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the project.
COPY geocoder.py gunicorn.py manage.py ./
COPY caddy ./caddy
COPY shack ./shack
# Run the application as the www-data user.
USER www-data
EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.py"]
