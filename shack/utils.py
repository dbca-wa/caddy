from django.contrib.gis.geos import GEOSGeometry
from django.db.migrations.operations.base import Operation
import ujson
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


def harvest_cadastre(limit=None):
    """Query the cadastre WFS for features. ``limit`` is optional integer of the
    maximum number of features to query.
    """
    GEOSERVER_URL = os.environ['GEOSERVER_URL']
    params = {
        'service': 'WFS',
        'version': '1.1.0',
        'request': 'GetFeature',
        'typeName': os.environ['CADASTRE_LAYER'],
        'outputFormat': 'application/json',
        'sortBy': 'ogc_fid',
        'maxFeatures': 1,
    }
    auth = (os.environ['GEOSERVER_USER'], os.environ['GEOSERVER_PASSWORD'])
    # Initially query cadastre for the total feature count (maxfeatures=1)
    # Iterate over the total, 1000 features at a time.
    r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
    total_features = r.json()['totalFeatures']
    if limit and limit < total_features:  # Optional limit on total features imported.
        total_features = limit
    params['maxFeatures'] = 1000
    if limit and limit < params['maxFeatures']:
        params['maxFeatures'] = limit
    for i in range(0, total_features, params['maxFeatures']):
        logger.info('Querying features {} to {}'.format(i, i + params['maxFeatures']))
        # Query the server for features, using startIndex.
        params['startIndex'] = i
        r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
        j = r.json()
        create_features = []
        updates = 0
        for f in j['features']:
            #  Query for an existing feature (PIN == object_id)
            if Address.objects.filter(object_id=f['properties']['pin']).exists():
                add = Address.objects.get(object_id=f['properties']['pin'])
                update = True  # Existing feature
            else:
                add = Address(object_id=f['properties']['pin'])
                update = False  # New feature
            poly = GEOSGeometry(ujson.dumps(f['geometry']))
            add.centroid = poly.centroid  # Precalculate the centroid.
            add.envelope = poly.envelope  # Simplify the geometry bounds.
            prop = f['properties']
            address_nice = ''  # Human-readable "nice" address.
            if 'survey_lot' in prop and prop['survey_lot']:
                add.data['survey_lot'] = prop['survey_lot']
                address_nice += '{} '.format(prop['survey_lot'])
            if 'addrs_no' in prop and prop['addrs_no']:
                add.data['address_no'] = int(prop['addrs_no'])
                address_nice += '{}'.format(prop['addrs_no'])
            if 'addrs_sfx' in prop and prop['addrs_sfx']:
                add.data['address_sfx'] = prop['addrs_sfx']
                address_nice += '{} '.format(prop['addrs_sfx'])
            else:  # No suffix - add a space instead.
                address_nice += ' '
            if 'road_name' in prop and prop['road_name']:
                if 'road_sfx' in prop and prop['road_sfx']:
                    add.data['road'] = '{} {}'.format(prop['road_name'], prop['road_sfx'])
                    address_nice += '{} '.format(prop['road_name'])
                    add.data['road_pfx'] = prop['road_name']
                    add.data['road_sfx'] = prop['road_sfx']
                    # Try to match an existing suffix.
                    if prop['road_sfx'] in ROADS_ABBREV:
                        address_nice += '{} '.format(ROADS_ABBREV[prop['road_sfx']])
                    else:
                        address_nice += '{} '.format(prop['road_sfx'])
                else:
                    add.data['road'] = prop['road_name']
                    address_nice += '{} '.format(prop['road_name'])
            if 'locality' in prop and prop['locality']:
                add.data['locality'] = prop['locality']
                address_nice += '{} '.format(prop['locality'])
            if 'postcode' in prop and prop['postcode']:
                add.data['postcode'] = prop['postcode']
                address_nice += '{} '.format(prop['postcode'])
            # Other fields:
            for f in ['strata', 'crn_allot', 'reserve', 'pin', 'landuse', 'res_no', 'res_class', 'res_vest']:
                if f in prop and prop[f]:
                    add.data[f] = prop[f]
            add.address_nice = address_nice.strip()
            add.address_text = add.get_address_text()
            if update:  # Save changes to existing features.
                add.save()
                updates += 1
            else:
                create_features.append(add)

        # Do a bulk_create for each iteration (new features only).
        Address.objects.bulk_create(create_features)
        logger.info('Created {} addresses, updated {}'.format(len(create_features), updates))


def harvest_state_cadastre(limit=None):
    """Refactor of harvest_cadastre to deal with new source schema.
    """
    GEOSERVER_URL = os.environ['GEOSERVER_URL']
    params = {
        'service': 'WFS',
        'version': '1.1.0',
        'request': 'GetFeature',
        'typeName': os.environ['CADASTRE_LAYER'],
        'outputFormat': 'application/json',
        'sortBy': 'ogc_fid',
        'maxFeatures': 1,
    }
    auth = (os.environ['GEOSERVER_USER'], os.environ['GEOSERVER_PASSWORD'])
    # Initially query cadastre for the total feature count (maxfeatures=1)
    # Iterate over the total, 1000 features at a time.
    r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
    total_features = r.json()['totalFeatures']
    if limit and limit < total_features:  # Optional limit on total features imported.
        total_features = limit
    params['maxFeatures'] = 1000
    if limit and limit < params['maxFeatures']:
        params['maxFeatures'] = limit
    for i in range(0, total_features, params['maxFeatures']):
        logger.info('Querying features {} to {}'.format(i, i + params['maxFeatures']))
        # Query the server for features, using startIndex.
        params['startIndex'] = i
        r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
        j = r.json()
        create_features = []
        updates = 0
        for f in j['features']:
            #  Query for an existing feature (PIN == object_id)
            if Address.objects.filter(object_id=f['properties']['cad_pin']).exists():
                add = Address.objects.get(object_id=f['properties']['cad_pin'])
                add.data = {}
                update = True  # Existing feature
            else:
                add = Address(object_id=f['properties']['cad_pin'])
                update = False  # New feature
            poly = GEOSGeometry(ujson.dumps(f['geometry']))
            add.centroid = poly.centroid  # Precalculate the centroid.
            add.envelope = poly.envelope  # Simplify the geometry bounds.
            prop = f['properties']
            address_nice = ''  # Human-readable "nice" address.
            if 'cad_lot_number' in prop and prop['cad_lot_number']:
                add.data['lot_number'] = prop['cad_lot_number']
                address_nice += 'Lot {} '.format(prop['cad_lot_number'])
            if 'cad_house_number' in prop and prop['cad_house_number']:
                add.data['house_number'] = prop['cad_house_number']
                address_nice += '{} '.format(prop['cad_house_number'])
            if 'cad_road_name' in prop and prop['cad_road_name']:
                add.data['road_name'] = prop['cad_road_name']
                address_nice += '{} '.format(prop['cad_road_name'])
                if 'cad_road_suffix' in prop and prop['cad_road_suffix']:
                    add.data['road_suffix'] = prop['cad_road_suffix']
                    # Try to match an existing suffix.
                    if prop['cad_road_suffix'] in ROADS_ABBREV:
                        address_nice += '{} '.format(ROADS_ABBREV[prop['cad_road_suffix']])
                    else:
                        address_nice += '{} '.format(prop['cad_road_suffix'])
            if 'cad_locality' in prop and prop['cad_locality']:
                add.data['locality'] = prop['cad_locality']
                address_nice += '{} '.format(prop['cad_locality'])
            if 'cad_postcode' in prop and prop['cad_postcode']:
                add.data['postcode'] = prop['cad_postcode']
                address_nice += '{} '.format(prop['cad_postcode'])
            if 'cad_owner_name' in prop and prop['cad_owner_name']:
                add.owner = prop['cad_owner_name']
            if 'cad_ownership' in prop and prop['cad_ownership']:
                add.data['ownership'] = prop['cad_ownership']
            if 'cad_pin' in prop and prop['cad_pin']:
                add.data['pin'] = prop['cad_pin']
            add.address_nice = address_nice.strip()
            add.address_text = add.get_address_text()
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
