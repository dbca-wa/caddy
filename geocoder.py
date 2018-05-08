#!/usr/bin/python
from bottle import Bottle, route, static_file, request, response
import confy
import ujson
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import bjoern


confy.read_environment_file()
database_url = confy.env('DATABASE_URL').replace('postgis', 'postgres')
engine = create_engine(database_url)
Session = scoped_session(sessionmaker(bind=engine, autoflush=True))
s = Session()
app = application = Bottle()


@app.route('/')
def index():
    return static_file('index.html', root='caddy/templates')


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
    sql = "SELECT address_nice, ST_X(centroid), ST_Y(centroid) FROM shack_address WHERE tsv @@ to_tsquery('{}')".format(words)
    result = s.execute(sql).fetchmany(int(limit))
    j = []
    if result:
        for i in result:
            j.append({
                'address': i[0],
                'lon': i[1],
                'lat': i[2]
            })
        return ujson.dumps(j)
    else:
        return '[]'


if __name__ == '__main__':
    bjoern.run(wsgi_app=app,host='0.0.0.0', port=confy.env('PORT', 8811), reuse_port=True)
