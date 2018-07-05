FROM python:3.6.6-slim-stretch
MAINTAINER asi@dbca.wa.gov.au

RUN apt-get update -y \
  && apt-get install -y wget gcc binutils libproj-dev gdal-bin
WORKDIR /usr/src/app
COPY geocoder.py gunicorn.ini manage.py requirements.txt ./
COPY caddy ./caddy
COPY shack ./shack
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.ini"]
