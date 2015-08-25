# Caddy

Caddy is a small experiment to harvest land parcel legal description
fields, denormalise/sanitise data and expose it as a searchable API
for geocoding via minimal Django application.

# Installation

* Clone the repository.
* Create a virtualenv and install requirements: `pip install -r
  requirements.txt`
* Define environment settings in `.env`.
* Create a database and run `honcho run python manage.py migrate`
* Run the management command to harvest data: `honcho run python
  manage.py harvest_cadastre`

# Environment settings

The following environment settings should be defined in a `.env` file
(used by `honcho`):

    DEBUG=True
    PORT=8080
    DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/NAME"
    SECRET_KEY="ThisIsASecretKey"
    GEOSERVER_URL="http://geoserver.dpaw.wa.gov.au/geoserver/ows"
    GEOSERVER_USER="username"
    GEOSERVER_PASSWORD="password"
    CADASTRE_LAYER="cddp:cadastre"

*NOTE*: the `GEOSERVER_*` settings are to a WFS service endpoint. The
`CADASTRE_LAYER` is the WFS workspace:layer.

# Usage

Run the application with `honcho start`. Visit the API url and provide a
query parameter `q` to search, e.g.:

    http://HOST/api/v1/address/geocode/?q=perth+wa&limit=5

Other API endpoints:

    http://HOST/api/v1/address/
    http://HOST/api/v1/address/schema/
