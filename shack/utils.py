from __future__ import unicode_literals, absolute_import
from django.contrib.gis.geos import GEOSGeometry
from django.db.migrations.operations.base import Operation
from django.template import Context, Template
import json
import logging
import os
import requests

from .models import Address

logger = logging.getLogger('caddy')


class LoadExtension(Operation):
    """Class to assist with loading PostgreSQL extension during migrations.
    """
    reversible = True

    def __init__(self, name):
        self.name = name

    def state_forwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS {}".format(self.name))

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute("DROP EXTENSION {}".format(self.name))

    def describe(self):
        return "Creates extension {}".format(self.name)


class CreateGinIndex(Operation):
    """Class to create a Postgres GIN index on a field.
    ALTER TABLE stack_cadastre ADD COLUMN textsearch_index_col tsvector;
    """
    reversible = True

    def __init__(self, idx_name, table, field):
        self.idx_name = idx_name
        self.table = table
        self.field = field

    def state_forwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute("CREATE INDEX {} ON {} USING gin(to_tsvector('english', {}))".format(self.idx_name, self.table, self.field))

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute("DROP INDEX {}".format(self.idx_name))

    def describe(self):
        return "Creates index {}".format(self.idx_name)


def harvest_cadastre(limit=None):
    """Query the cadastre WFS for features. ``limit`` is optional integer of the
    maximum number of features to query.
    """
    GEOSERVER_URL = os.environ['GEOSERVER_URL']
    CADASTRE_LAYER = os.environ['CADASTRE_LAYER']
    url = '{}?service=WFS&version=1.1.0&request=GetFeature&typeName={}&outputFormat=application/json'.format(
        GEOSERVER_URL, CADASTRE_LAYER)
    auth = (os.environ['GEOSERVER_USER'], os.environ['GEOSERVER_PASSWORD'])
    f = open('shack/templates/shack/address_text.txt').read()
    template = Template(f)
    # Initially query cadastre for the total features (maxFeatures=1)
    # Iterate over the total, 10000 features at a time.
    r = requests.get(url=url + '&maxFeatures=1', auth=auth)
    total_features = r.json()['totalFeatures']
    if limit and limit < total_features:  # Optional limit on total features imported.
        total_features = limit
    max_features = 10000
    if limit and limit < max_features:
        max_features = limit
    for i in range(0, total_features, 10000):
        logger.info('Querying features {} to {}'.format(i, max_features + i))
        # Query the server for features, using startIndex.
        q = url + '&maxFeatures={}&startIndex={}'.format(max_features, i)
        r = requests.get(url=q, auth=auth)
        j = r.json()
        create_features = []
        updates = 0
        for f in j['features']:
            #  Query for an existing feature (id == object_id)
            if Address.objects.filter(object_id=f['id']).exists():
                add = Address.objects.get(object_id=f['id'])
                update = True  # Existing feature
            else:
                add = Address(object_id=f['id'])
                update = False  # New feature
            poly = GEOSGeometry(json.dumps(f['geometry']))
            add.centroid = poly.centroid  # Precalculate the centroid.
            add.envelope = poly.envelope  # Simplify the geometry bounds.
            prop = f['properties']
            add.lot_no = prop['lot_no']
            if prop['addrs_no']:
                add.address_no = int(prop['addrs_no'])
            add.address_sfx = prop['addrs_sfx']
            add.road = prop['road_name']
            add.road_sfx = prop['road_sfx']
            add.locality = prop['locality']
            add.postcode = prop['postcode']
            add.survey_lot = prop['survey_lot']
            add.strata = prop['strata']
            add.reserve = prop['reserve']
            # Construct a "nice", human-friendly address string.
            address_nice = ''
            if 'lot_no' in prop and prop['lot_no']:
                address_nice += 'Lot {} '.format(prop['lot_no'])
            if 'addrs_no' in prop and prop['addrs_no']:
                if 'addrs_sfx' in prop and prop['addrs_sfx']:
                    address_nice += '{}{} '.format(prop['addrs_no'], prop['addrs_sfx'])
                else:
                    address_nice += '{} '.format(prop['addrs_no'])
            if 'road_name' in prop and prop['road_name']:
                address_nice += '{} '.format(prop['road_name'])
            if 'road_sfx' in prop and prop['road_sfx']:
                # Try to match an existing suffix.
                if prop['road_sfx'] in ROADS_ABBREV:
                    address_nice += '{} '.format(ROADS_ABBREV[prop['road_sfx']])
                else:
                    address_nice += '{} '.format(prop['road_sfx'])
            if 'locality' in prop and prop['locality']:
                address_nice += '{} '.format(prop['locality'])
            if 'postcode' in prop and prop['postcode']:
                address_nice += '{} '.format(prop['postcode'])
            add.address_nice = address_nice.strip()
            # Render the address_text field
            context = Context({'object': add})
            add.address_text = template.render(context)
            if update:  # Save changes to existing features.
                add.save()
                updates += 1
            else:
                create_features.append(add)

        # Do a bulk_create for each iteration (new features only).
        Address.objects.bulk_create(create_features)
        logger.info('Created {} addresses, updated {}'.format(len(create_features), updates))


# Source: http://www.ipaustralia.gov.au/about-us/doing-business-with-us/address-standards/
ROADS_ABBREV = {
    'ACCS': 'ACCESS',
    'ALLY': 'ALLEY',
    'ALWY': 'ALLEYWAY',
    'AMBL': 'AMBLE',
    'ANCG': 'ANCHORAGE',
    'APP': 'APPROACH',
    'ARC': 'ARCADE',
    'ART': 'ARTERY',
    'AV': 'AVENUE',
    'AVE': 'AVENUE',
    'BASN': 'BASIN',
    'BCH': 'BEACH',
    'BLK': 'BLOCK',
    'BVD': 'BOULEVARD',
    'BR': 'BRANCH',
    'BRCE': 'BRACE',
    'BRK': 'BREAK',
    'BDGE': 'BRIDGE',
    'BDWY': 'BROADWAY',
    'BYPA': 'BYPASS',
    'BYWY': 'BYWAY',
    'CAUS': 'CAUSEWAY',
    'CTR': 'CENTRE',
    'CNWY': 'CENTREWAY',
    'CH': 'CHASE',
    'CIR': 'CIRCLE',
    'CLT': 'CIRCLET',
    'CCT': 'CIRCUIT',
    'CRCS': 'CIRCUS',
    'CL': 'CLOSE',
    'CLDE': 'COLONNADE',
    'CMMN': 'COMMON',
    'CON': 'CONCOURSE',
    'CPS': 'COPSE',
    'CNR': 'CORNER',
    'CSO': 'CORSO',
    'CT': 'COURT',
    'CTYD': 'COURTYARD',
    'CR': 'CRESCENT',
    'CRES': 'CRESCENT',
    'CRST': 'CREST',
    'CRSS': 'CROSS',
    'CRSG': 'CROSSING',
    'CRD': 'CROSSROAD',
    'COWY': 'CROSSWAY',
    'CUWY': 'CRUISEWAY',
    'CDS': 'CUL-DE-SAC',
    'CTTG': 'CUTTING',
    'DEVN': 'DEVIATION',
    'DSTR': 'DISTRIBUTOR',
    'DR': 'DRIVE',
    'DRWY': 'DRIVEWAY',
    'ELB': 'ELBOW',
    'ENT': 'ENTRANCE',
    'ESP': 'ESPLANADE',
    'EST': 'ESTATE',
    'EXP': 'EXPRESSWAY',
    'EXTN': 'EXTENSION',
    'FAWY': 'FAIRWAY',
    'FTRK': 'FIRE TRACK',
    'FITR': 'FIRETRAIL',
    'FOLW': 'FOLLOW',
    'FTWY': 'FOOTWAY',
    'FSHR': 'FORESHORE',
    'FORM': 'FORMATION',
    'FWY': 'FREEWAY',
    'FRNT': 'FRONT',
    'FRTG': 'FRONTAGE',
    'GDN': 'GARDEN',
    'GDNS': 'GARDENS',
    'GTE': 'GATE',
    'GTES': 'GATES',
    'GLD': 'GLADE',
    'GLDE': 'GLADE',
    'GRA': 'GRANGE',
    'GRN': 'GREEN',
    'GRND': 'GROUND',
    'GR': 'GROVE',
    'GLY': 'GULLY',
    'HTS': 'HEIGHTS',
    'HRD': 'HIGHROAD',
    'HWY': 'HIGHWAY',
    'INTG': 'INTERCHANGE',
    'INTN': 'INTERSECTION',
    'JNC': 'JUNCTION',
    'LDG': 'LANDING',
    'LNWY': 'LANEWAY',
    'LEES': 'LEES',
    'LT': 'LITTLE',
    'LKT': 'LOOKOUT',
    'LWR': 'LOWER',
    'MNDR': 'MEANDER',
    'MWY': 'MOTORWAY',
    'MT': 'MOUNT',
    'OTLK': 'OUTLOOK',
    'PDE': 'PARADE',
    'PKLD': 'PARKLANDS',
    'PWY': 'PARKWAY',
    'PKWY': 'PARKWAY',
    'PHWY': 'PATHWAY',
    'PIAZ': 'PIAZZA',
    'PL': 'PLACE',
    'PLAT': 'PLATEAU',
    'PLZA': 'PLAZA',
    'PKT': 'POCKET',
    'PNT': 'POINT',
    'PROM': 'PROMENADE',
    'QDGL': 'QUADRANGLE',
    'QDRT': 'QUADRANT',
    'QY': 'QUAY',
    'QYS': 'QUAYS',
    'RMBL': 'RAMBLE',
    'RAMP': 'RAMP',
    'RNGE': 'RANGE',
    'RCH': 'REACH',
    'RES': 'RESERVE',
    'RTT': 'RETREAT',
    'RDGE': 'RIDGE',
    'RGWY': 'RIDGEWAY',
    'ROWY': 'RIGHT OF WAY',
    'RVR': 'RIVER',
    'RVWY': 'RIVERWAY',
    'RVRA': 'RIVIERA',
    'RD': 'ROAD',
    'RDS': 'ROADS',
    'RDSD': 'ROADSIDE',
    'RDWY': 'ROADWAY',
    'RNDE': 'RONDE',
    'RSBL': 'ROSEBOWL',
    'RTY': 'ROTARY',
    'RND': 'ROUND',
    'RTE': 'ROUTE',
    'SWY': 'SERVICE WAY',
    'SDNG': 'SIDING',
    'SLPE': 'SLOPE',
    'SND': 'SOUND',
    'SQ': 'SQUARE',
    'STRS': 'STAIRS',
    'SHWY': 'STATE HIGHWAY',
    'STPS': 'STEPS',
    'STRA': 'STRAND',
    'ST': 'STREET',
    'STRP': 'STRIP',
    'SBWY': 'SUBWAY',
    'TCE': 'TERRACE',
    'THOR': 'THOROUGHFARE',
    'TLWY': 'TOLLWAY',
    'TWRS': 'TOWERS',
    'TRK': 'TRACK',
    'TRL': 'TRAIL',
    'TRLR': 'TRAILER',
    'TRI': 'TRIANGLE',
    'TKWY': 'TRUNKWAY',
    'UPAS': 'UNDERPASS',
    'UPR': 'UPPER',
    'VDCT': 'VIADUCT',
    'VLLS': 'VILLAS',
    'VSTA': 'VISTA',
    'WKWY': 'WALKWAY',
    'WHRF': 'WHARF',
    'WYND': 'WYND',
}
