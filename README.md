# Caddy

Caddy is a small application to harvest land parcel legal description
fields and index address data via minimal a Django application.

## Installation

The recommended way to set up this project for development is using
[uv](https://docs.astral.sh/uv/)
to install and manage a Python virtual environment.
With uv installed, change into the project directory and run:

    uv sync

Activate the virtualenv like so:

    source .venv/bin/activate

To run Python commands in the activated virtualenv, thereafter run them like so:

    python manage.py shell_plus

Manage new or updated project dependencies with uv also, like so:

    uv add newpackage==1.0

## Environment settings

This project uses environment variables (in a `.env` file) to define application settings.
Required settings are as follows:

    DATABASE_URL=postgres://USER:PASSWORD@HOST:PORT/NAME
    SECRET_KEY=ThisIsASecretKey
    AZURE_ACCOUNT_NAME=azureaccountname
    AZURE_ACCOUNT_KEY=azureaccountsecret
    AZURE_CONTAINER=containername

## Background

The **shack** application contains a single model, **Address**. This model
is used to store the relevant address fields of the cadastre dataset,
plus each land parcel's centroid and spatial bounds. A utility script in
**shack/utils.py** is used to query the cadastre WFS layer to mirror the
data. Address fields are rendering into a single document, stored in the
_address_text_ field.

The full text search in this project leverages PostgreSQL features for
parsing and normalising text documents. A custom Django migration has been
written to create a _tsvector_ column in the Address table to store
precalculated tsvector values for each address document, plus a GIN index
on that field and a database trigger to update the index on insert or update.

The API endpoint to geocode addresses is a custom view that uses raw SQL
to query the tsvector field and return any results. Returned data is
deliberately limited to a "human readable" address, object centroid and
bounding box.

Further reference:
<http://www.postgresql.org/docs/current/static/textsearch.html>

## Pre-commit hooks

This project includes the following pre-commit hooks:

- TruffleHog: https://docs.trufflesecurity.com/docs/scanning-git/precommit-hooks/

Pre-commit hooks may have additional system dependencies to run. Optionally
install pre-commit hooks locally like so:

    pre-commit install

Reference: <https://pre-commit.com/>
