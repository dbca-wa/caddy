# Caddy

Caddy is a small application to harvest land parcel legal description
fields and index address data via minimal a Django application, and
expose it as a searchable API for geocoding.

# Installation

The recommended way to set up this project for development is using
[Poetry](https://python-poetry.org/docs/) to install and manage a virtual Python
environment. With Poetry installed, change into the project directory and run:

    poetry install

To run Python commands in the virtualenv, thereafter run them like so:

    poetry run python manage.py

Manage new or updating project dependencies with Poetry also, like so:

    poetry add newpackage==1.0

# Environment settings

This project uses environment variables (in a `.env` file) to define application settings.
Required settings are as follows:

    DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/NAME"
    SECRET_KEY="ThisIsASecretKey"

Optional variables below may also need to be defined (context-dependent):

    ALLOWED__DOMAINS=".domain.com"
    GEOSERVER_URL="https://geoserver.service.url/"
    GEOSERVER_USER="username"
    GEOSERVER_PASSWORD="password"
    CADASTRE_LAYER="workspace:layer"

*NOTE*: the `GEOSERVER_*` settings are to a WFS service endpoint. The
`CADASTRE_LAYER` is the WFS layer (**workspace:layer**).

# Usage

Run the frontend application with `poetry run python geocoder.py` (the default port
is 8081, which can be overridden by defining a `PORT` environment variable.

Run Django console commands manually:

    poetry run python manage.py shell_plus

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
http://www.postgresql.org/docs/current/static/textsearch.html

# Pre-commit hooks

This project includes the following pre-commit hooks:

- TruffleHog: https://docs.trufflesecurity.com/docs/scanning-git/precommit-hooks/

Pre-commit hooks may have additional system dependencies to run. Optionally
install pre-commit hooks locally like so:

    poetry run pre-commit install

Reference: https://pre-commit.com/
