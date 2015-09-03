# Caddy

Caddy is a small experiment to harvest land parcel legal description
fields, index address data and expose it as a searchable API
for geocoding via minimal a Django application.

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
`CADASTRE_LAYER` is the WFS layer (**workspace:layer**).

# Usage

Run the application with `honcho start`. Visit the API url and provide a
query parameter `q` to search, e.g.:

    http://HOST/api/v1/address/geocode/?q=perth+wa&limit=5

Other API endpoints:

    http://HOST/api/v1/address/
    http://HOST/api/v1/address/schema/

# Background

The **shack** application contains a single model, **Address**. This model
is used to store the relevant address fields of the cadastre dataset,
plus each land parcel's centroid and spatial bounds. A utility script in
**shack/utils.py** is used to query the cadastre WFS layer to mirror the
data. Address fields are rendering into a single document, stored in the
*address_text* field.

The full text search in this project leverages PostgreSQL features for
parsing and normalising text documents. A custom Django migration has been
written to create a *tsvector* column in the Address table to store
precalculated tsvector values for each address document, plus a GIN index
on that field and a database trigger to update the index on insert or update.

The API endpoint to geocode addresses is a custom view that uses raw SQL
to query the tsvector field and return any results. Returned data is
deliberately limited to a "human readable" address, object centroid and
bounding box.

Further reference:
http://www.postgresql.org/docs/9.3/static/textsearch.html
