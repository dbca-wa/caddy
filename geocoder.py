#!/usr/bin/python
from bottle import Bottle, route, static_file, request, response
from caddy.utils import env
import os
import ujson
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session


dot_env = os.path.join(os.getcwd(), '.env')
if os.path.exists(dot_env):
    from dotenv import read_dotenv
    read_dotenv()
database_url = env('DATABASE_URL').replace('postgis', 'postgres')
engine = create_engine(database_url)
Session = scoped_session(sessionmaker(bind=engine, autoflush=True))
app = application = Bottle()


@app.route('/')
def index():
    return static_file('index.html', root='caddy/templates')


@app.route('/api/<object_id>')
def detail(object_id):
    response.content_type = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    sql = "SELECT object_id, address_nice, owner, ST_AsText(centroid), ST_AsText(envelope), data FROM shack_address WHERE object_id = '{}'".format(object_id)
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
            'data': result[5],
        })
    else:
        return '{}'

@app.route('/api/geocode')
def geocode():
    response.content_type = 'application/json'
    # Allow cross-origin GET requests.
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
    q = request.query.q or ''
    if not q:
        return '[]'
    limit = request.query.limit or 5
    words = q.split()
    words = ' & '.join(words)
    # Partial address searching
    sql = "SELECT address_nice, owner, ST_X(centroid), ST_Y(centroid) FROM shack_address WHERE tsv @@ to_tsquery('{}')".format(words)
    s = Session()
    result = s.execute(sql).fetchmany(int(limit))
    s.close()
    j = []
    if result:
        for i in result:
            j.append({
                'address': i[0],
                'owner': i[1],
                'lon': i[2],
                'lat': i[3]
            })
        return ujson.dumps(j)
    else:
        return '[]'


if __name__ == '__main__':
    from bottle import run
    run(application, host='0.0.0.0', port=env('PORT', 8811))
