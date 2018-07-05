FROM python:3.6.6-slim-stretch
MAINTAINER asi@dbca.wa.gov.au

RUN apt-get update -y \
  && apt-get install -y wget gcc binutils libproj-dev gdal-bin
#RUN apk update \
#  && apk upgrade \
#  && apk add --no-cache --virtual .build-deps postgresql-dev gcc python3-dev musl-dev \
#  && apk add --no-cache libpq bash binutils gdal libproj
WORKDIR /usr/src/app
COPY geocoder.py gunicorn.ini manage.py requirements.txt ./
COPY caddy ./caddy
COPY shack ./shack
RUN pip install --no-cache-dir -r requirements.txt
#RUN apk del .build-deps

EXPOSE 8080
CMD ["gunicorn", "caddy.wsgi", "--config", "gunicorn.ini"]
