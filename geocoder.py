#!/usr/bin/python
from bottle import Bottle, static_file, request, response
from caddy.utils import env
import os
import re
import ujson
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session


dot_env = os.path.join(os.getcwd(), '.env')
if os.path.exists(dot_env):
    from dotenv import load_dotenv
    load_dotenv()
database_url = env('DATABASE_URL').replace('postgis', 'postgresql')
engine = create_engine(database_url)
Session = scoped_session(sessionmaker(bind=engine, autoflush=True))
app = application = Bottle()
lon_lat = re.compile(r'(?P<lon>-?[0-9]+.[0-9]+),\s*(?P<lat>-?[0-9]+.[0-9]+)')


@app.route('/')
def index():
    return static_file('index.html', root='caddy/templates')


@app.route('/liveness')
def liveness():
    response.content_type = 'application/json'
    return '{"liveness": "OK"}'


@app.route('/readiness')
def readiness():
    sql = 'SELECT 1'
    s = Session()
    result = s.execute(sql).fetchone()
    s.close()
    if result:
        response.content_type = 'application/json'
        return '{"readiness": "OK"}'


@app.route('/api/<object_id>')
def detail(object_id):
    response.content_type = 'application/json'
    sql = f"SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), ST_AsText(boundary), data FROM shack_address WHERE object_id = '{object_id}'"
    s = Session()
    result = s.execute(sql).fetchone()
    s.close()
    if result:
        return ujson.dumps({
            'object_id': result[0],
            'address': result[1],
            'owner': result[2],
            'centroid': result[3],
            'envelope': result[4],
            'boundary': result[5],
            'data': result[6],
        })
    else:
        return '{}'


@app.route('/api/geocode')
def geocode():
    response.content_type = 'application/json'
    q = request.query.q or ''
    point = request.query.point or ''
    limit = request.query.limit or 5
    if not q and not point:
        return '[]'
    # Point intersection query
    if point:  # Must be in the format lon,lat
        m = lon_lat.match(point)
        if m:
            lon, lat = m.groups()
            sql = f"SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), ST_AsText(boundary), data FROM shack_address WHERE ST_Intersects(boundary, ST_GeomFromEWKT('SRID=4326;POINT({lon} {lat})'))"
            s = Session()
            result = s.execute(sql).fetchone()
            s.close()
            if result:
                return ujson.dumps({
                    'object_id': result[0],
                    'address': result[1],
                    'owner': result[2],
                    'centroid': result[3],
                    'envelope': result[4],
                    'boundary': result[5],
                    'data': result[6],
                })
            else:
                return '{}'
        else:
            return '[]'
    # Address query
    words = q.split()
    words = ' & '.join(words)
    sql = f"SELECT address_nice, owner, ST_X(centroid), ST_Y(centroid), object_id FROM shack_address WHERE tsv @@ to_tsquery('{words}')"
    s = Session()
    result = s.execute(sql).fetchmany(int(limit))
    s.close()
    if result:
        j = []
        for i in result:
            j.append({
                'address': i[0],
                'owner': i[1],
                'lon': i[2],
                'lat': i[3],
                'pin': i[4],
            })
        return ujson.dumps(j)
    else:
        return '[]'


if __name__ == '__main__':
    from bottle import run
    run(application, host='0.0.0.0', port=env('PORT', 8811))
