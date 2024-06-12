#!/usr/bin/python
from bottle import Bottle, static_file, request, response
from caddy.utils import env
import os
import re
import ujson
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.sql import text


dot_env = os.path.join(os.getcwd(), ".env")
if os.path.exists(dot_env):
    from dotenv import load_dotenv
    load_dotenv()
database_url = env("DATABASE_URL").replace("postgis", "postgresql+psycopg")
engine = create_engine(database_url)
Session = scoped_session(sessionmaker(bind=engine, autoflush=True))
app = application = Bottle()
lon_lat = re.compile(r"(?P<lon>-?[0-9]+.[0-9]+),\s*(?P<lat>-?[0-9]+.[0-9]+)")


@app.route("/")
def index():
    return static_file("index.html", root="caddy/templates")


@app.route("/livez")
def liveness():
    response.content_type = "application/json"
    return "{'liveness': 'OK'}"


@app.route("/readyz")
def readiness():
    s = Session()
    cursor = s.execute(text("SELECT 1"))
    result = cursor.fetchone()
    s.close()
    if result:
        response.content_type = "application/json"
        return "{'readiness': 'OK'}"


@app.route("/api/<object_id>")
def detail(object_id):
    # Validate `object_id`: this value needs be castable as an integer, even though we use it as a string.
    try:
        int(object_id)
    except ValueError:
        return "{}"

    response.content_type = "application/json"
    sql = text(f"""SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), ST_AsText(boundary), data
               FROM shack_address
               WHERE object_id = :object_id""")
    sql = sql.bindparams(object_id=object_id)
    s = Session()
    cursor = s.execute(sql)
    result = cursor.fetchone()
    s.close()

    if result:
        return ujson.dumps({
            "object_id": result[0],
            "address": result[1],
            "owner": result[2],
            "centroid": result[3],
            "envelope": result[4],
            "boundary": result[5],
            "data": result[6],
        })
    else:
        return "{}"


@app.route("/api/geocode")
def geocode():
    response.content_type = "application/json"
    q = request.query.q or ""
    point = request.query.point or ""
    if not q and not point:
        return "[]"

    # Point intersection query
    if point:  # Must be in the format lon,lat
        m = lon_lat.match(point)
        if m:
            lon, lat = m.groups()
            # Validate `lon` and `lat` by casting them to float values.
            try:
                lon, lat = float(lon), float(lat)
            except ValueError:
                return "{}"
            ewkt = f"SRID=4326;POINT({lon} {lat})"
            sql = text("""SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), ST_AsText(boundary), data
                       FROM shack_address
                       WHERE ST_Intersects(boundary, ST_GeomFromEWKT(:ewkt))""")
            sql = sql.bindparams(ewkt=ewkt)
            s = Session()
            cursor = s.execute(sql)
            result = cursor.fetchone()
            s.close()
            if result:
                return ujson.dumps({
                    "object_id": result[0],
                    "address": result[1],
                    "owner": result[2],
                    "centroid": result[3],
                    "envelope": result[4],
                    "boundary": result[5],
                    "data": result[6],
                })
            else:
                return "{}"
        else:
            return "[]"

    # Address query
    # Default to return a maximum of five results, allow override via `limit`.
    if request.query.limit:
        try:
            limit = int(request.query.limit)
        except ValueError:
            return "[]"
    else:
        limit = 5
    # Sanitise the input query: remove any non-alphanumeric characters, replace any multiple with single whitespace.
    pattern = r"[^A-Za-z0-9]+"
    q = re.sub(pattern, "", q)
    words = q.split()
    words = " & ".join(words)
    sql = text(f"""SELECT address_nice, owner, ST_X(centroid), ST_Y(centroid), object_id
               FROM shack_address
               WHERE tsv @@ to_tsquery(:words)""")
    sql = sql.bindparams(words=words)
    s = Session()
    cursor = s.execute(sql)
    result = cursor.fetchone()
    result = cursor.fetchmany(limit)
    s.close()
    if result:
        j = []
        for i in result:
            j.append({
                "address": i[0],
                "owner": i[1],
                "lon": i[2],
                "lat": i[3],
                "pin": i[4],
            })
        return ujson.dumps(j)
    else:
        return "[]"


if __name__ == "__main__":
    from bottle import run
    run(application, host="0.0.0.0", port=env("PORT", 8211))
