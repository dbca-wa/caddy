#!/usr/bin/python
import os
import re

import orjson
from bottle import Bottle, HTTPResponse, request, response, static_file
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text

from caddy.utils import env

dot_env = os.path.join(os.getcwd(), ".env")
if os.path.exists(dot_env):
    from dotenv import load_dotenv

    load_dotenv()
app = application = Bottle()


# Database connection - create a DB engine and a scoped session for queries.
# https://docs.sqlalchemy.org/en/20/orm/contextual.html#unitofwork-contextual
database_url = env("DATABASE_URL").replace("postgis", "postgresql+psycopg")
db_engine = create_engine(database_url)
Session = sessionmaker(bind=db_engine, autoflush=True)

# Regex patterns
LON_LAT_PATTERN = re.compile(r"(?P<lon>-?[0-9]+.[0-9]+),\s*(?P<lat>-?[0-9]+.[0-9]+)")
ALPHANUM_PATTERN = re.compile(r"[^A-Za-z0-9\s]+")


@app.route("/")
def index():
    return static_file("index.html", root="caddy/templates")


@app.route("/favicon.ico")
def favicon():
    return static_file("favicon.ico", root="caddy/static")


@app.route("/livez")
def liveness():
    return "OK"


@app.route("/readyz")
def readiness():
    try:
        with Session.begin() as session:
            session.execute(text("SELECT 1")).fetchone()
        return "OK"
    except:
        return HTTPResponse(status=500, body="Error")


@app.route("/api/<object_id>")
def detail(object_id):
    """This route will return details of a single land parcel, serialised as a JSON object."""
    # Validate `object_id`: this value needs be castable as an integer, even though we handle it as a string.
    try:
        int(object_id)
    except ValueError:
        response.status = 400
        return "Bad request"

    response.content_type = "application/json"
    sql = text("""SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), ST_AsText(boundary), data
               FROM shack_address
               WHERE object_id = :object_id""")
    sql = sql.bindparams(object_id=object_id)
    with Session.begin() as session:
        result = session.execute(sql).fetchone()

    if result:
        return orjson.dumps(
            {
                "object_id": result[0],
                "address": result[1],
                "owner": result[2],
                "centroid": result[3],
                "envelope": result[4],
                "boundary": result[5],
                "data": result[6],
            }
        )
    else:
        return "{}"


@app.route("/api/geocode")
def geocode():
    """This route will accept a query parameter (`q` or `point`), and query for matching land parcels.
    `point` must be a string that parses as <float>,<float> and will be used to query for intersection with the `boundary`
    spatial column.
    `q` will be parsed as free text (non-alphanumeric characters will be ignored) and will be used to perform a text search
    against the `tsv` column.
    Query results will be returned as serialised JSON objects.
    An optional `limit` parameter may be passed in to limit the maximum number of results returned, otherwise the route
    defaults to a maximum of five results (no sorting is carried out, so these are simply the first five results from the
    query.
    """
    q = request.query.q or ""
    point = request.query.point or ""
    if not q and not point:
        response.status = 400
        return "Bad request"

    # Point intersection query
    if point:  # Must be in the format lon,lat
        m = LON_LAT_PATTERN.match(point)
        if m:
            lon, lat = m.groups()
            # Validate `lon` and `lat` by casting them to float values.
            try:
                lon, lat = float(lon), float(lat)
            except ValueError:
                response.status = 400
                return "Bad request"

            ewkt = f"SRID=4326;POINT({lon} {lat})"
            sql = text("""SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), ST_AsText(boundary), data
                       FROM shack_address
                       WHERE ST_Intersects(boundary, ST_GeomFromEWKT(:ewkt))""")
            sql = sql.bindparams(ewkt=ewkt)
            with Session.begin() as session:
                result = session.execute(sql).fetchone()

            # Serialise and return any query result.
            response.content_type = "application/json"
            if result:
                return orjson.dumps(
                    {
                        "object_id": result[0],
                        "address": result[1],
                        "owner": result[2],
                        "centroid": result[3],
                        "envelope": result[4],
                        "boundary": result[5],
                        "data": result[6],
                    }
                )
            else:
                return "{}"
        else:
            response.status = 400
            return "Bad request"

    # Address query
    # Sanitise the input query: remove any non-alphanumeric/whitespace characters.
    q = re.sub(ALPHANUM_PATTERN, "", q)
    words = q.split()  # Split words on whitespace.
    tsquery = "&".join(words)

    # Default to return a maximum of five results, allow override via `limit`.
    if request.query.limit:
        try:
            limit = int(request.query.limit)
        except ValueError:
            response.status = 400
            return "Bad request"
    else:
        limit = 5

    sql = text("""SELECT address_nice, owner, ST_X(centroid), ST_Y(centroid), object_id
               FROM shack_address
               WHERE tsv @@ to_tsquery(:tsquery)
               LIMIT :limit""")
    sql = sql.bindparams(tsquery=tsquery, limit=limit)
    with Session.begin() as session:
        result = session.execute(sql).fetchall()

    # Serialise and return any query results.
    response.content_type = "application/json"
    if result:
        j = []
        for i in result:
            j.append(
                {
                    "address": i[0],
                    "owner": i[1],
                    "lon": i[2],
                    "lat": i[3],
                    "pin": i[4],
                }
            )
        return orjson.dumps(j)
    else:
        return "[]"


if __name__ == "__main__":
    from bottle import run

    run(application, host="0.0.0.0", port=env("PORT", 8080))
