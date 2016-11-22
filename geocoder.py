from bottle import route, request, response, run
import confy
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session


confy.read_environment_file()
engine = create_engine(confy.env('DATABASE_URL'))
Session = scoped_session(sessionmaker(bind=engine))
s = Session()


@route('/api/geocode')
def geocode():
    response.content_type = 'application/json'
    q = request.query.q or ''
    if not q:
        return '[]'
    words = q.split()
    words = ' & '.join(words)
    # Partial address searching
    sql = "SELECT address_nice, ST_X(centroid), ST_Y(centroid) FROM shack_address WHERE tsv @@ to_tsquery('{}')".format(words)
    print(sql)
    result = s.execute(sql).fetchmany(5)  # Return up to 5 results.
    j = []
    if result:
        for i in result:
            j.append({
                'address': i[0],
                'lon': i[1],
                'lat': i[2]
            })
        return json.dumps(j)
    else:
        return '[]'


run(host='0.0.0.0', port=confy.env('PORT', 8811), debug=confy.env('DEBUG', False))
