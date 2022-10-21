from django.core.paginator import Paginator
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon, Point
from django.db.migrations.operations.base import Operation
from django.db.models import Subquery
import logging
import ujson
import os
import re
import requests

from cddp.models import CptCadastreScdb
from .models import Address

LOGGER = logging.getLogger('caddy')


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


def geocode(query, limit=None):
    """Convenience function to query Address objects for a text string and return a subset of the
    queryset object values.
    """
    qs = Address.objects.filter(address_text__search=query)
    resp = []
    if limit:
        qs = qs[0:limit]
    for address in qs:
        resp.append({
            'address': address.address_nice,
            'owner': address.owner,
            'lon': address.centroid.x,
            'lat': address.centroid.y
        })
    return resp


def harvest_state_cadastre(limit=None):
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
        'sortBy': 'cad_pin',
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
        LOGGER.info(f"Querying features {i} to {i + params['maxFeatures']}")
        # Query the server for features, using startIndex.
        params['startIndex'] = i
        r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
        j = r.json()
        create_features = []
        updates = 0
        suspect = 0
        skipped = 0
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
            # Edge case: sometimes features are returned as MultiPolygon.
            # If the feature is a MP containing one polygon feature, use that.
            # Otherwise, skip the feature entirely.
            if isinstance(poly, MultiPolygon) and len(poly) == 1:
                poly = poly[0]
            elif isinstance(poly, MultiPolygon) and len(poly) > 1:
                LOGGER.info(f"Skipping feature with PIN {f['properties']['cad_pin']} (multipolygon with >1 feature)")
                skipped += 1
                continue
            add.centroid = poly.centroid  # Precalculate the centroid.
            # Edge case: we've had some "zero area" geometries.
            if isinstance(poly.envelope, Point):
                LOGGER.info(f"Feature with PIN {f['properties']['cad_pin']} has area of 0 (geometry: {f['geometry']})")
                add.envelope = None
                suspect += 1
            else:
                add.envelope = poly.envelope  # Simplify the geometry bounds.
            prop = f['properties']
            address_nice = ''  # Human-readable "nice" address.
            if 'cad_lot_number' in prop and prop['cad_lot_number']:
                add.data['lot_number'] = prop['cad_lot_number']
                address_nice += '(Lot {}) '.format(prop['cad_lot_number'])
            if 'cad_house_number' in prop and prop['cad_house_number']:
                add.data['house_number'] = prop['cad_house_number']
                address_nice += '{} '.format(prop['cad_house_number'])
            if 'cad_road_name' in prop and prop['cad_road_name']:
                add.data['road_name'] = prop['cad_road_name']
                address_nice += '{} '.format(prop['cad_road_name'])
                if 'cad_road_type' in prop and prop['cad_road_type']:
                    add.data['road_type'] = prop['cad_road_type']
                    # Try to match an existing suffix.
                    if prop['cad_road_type'] in ROADS_ABBREV:
                        address_nice += '{} '.format(ROADS_ABBREV[prop['cad_road_type']])
                    else:
                        address_nice += '{} '.format(prop['cad_road_type'])
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
        LOGGER.info(f'Created {len(create_features)} addresses, updated {updates}, skipped {skipped}, suspect {suspect}')


def prune_addresses():
    """Delete any Addresses having an object_id value that doesn't match any current Cadastre object PIN.
    """
    addresses = set([int(i) for i in Address.objects.all().values_list('object_id', flat=True)])
    cadastres = set(CptCadastreScdb.objects.all().values_list('cad_pin', flat=True))
    to_delete = addresses - cadastres

    LOGGER.info(f'Deleting {len(to_delete)} Address objects not matching any current Cadastre object PIN')
    addresses = Address.objects.filter(object_id__in=to_delete)
    addresses.delete()


def copy_cddp_cadastre(queryset):
    """Copy Cadastre features from a database queryset.
    """
    created = 0
    updates = 0
    suspect = 0
    skipped = 0
    reserve_pattern = re.compile('(?P<reserve>[0-9]+)$')
    paginator = Paginator(queryset, 10000)

    for page_num in paginator.page_range:
        subquery = CptCadastreScdb.objects.filter(objectid__in=Subquery(paginator.page(page_num).object_list.values('objectid')))
        LOGGER.info(f'Importing {subquery.count()} cadastre addresses')
        for f in subquery:
            #  Query for an existing feature (PIN == object_id)
            if Address.objects.filter(object_id=str(f.cad_pin)).exists():
                add = Address.objects.get(object_id=str(f.cad_pin))
                add.data = {}
                update = True  # Existing feature
            else:
                add = Address(object_id=str(f.cad_pin))
                update = False  # New feature

            # Sometimes features are MultiPolygon, sometime Polygon.
            # If the feature is a MP containing one polygon feature, use that.
            # If >1, skip the feature.
            if isinstance(f.shape, Polygon):
                add.centroid = f.shape.centroid
                add.envelope = f.shape.envelope
                add.boundary = f.shape
            elif isinstance(f.shape, MultiPolygon) and len(f.shape) == 1:
                add.centroid = f.shape[0].centroid
                add.envelope = f.shape[0].envelope
                add.boundary = f.shape[0]
            elif isinstance(f.shape, MultiPolygon) and len(f.shape) > 1:
                LOGGER.info(f'Skipping feature with PIN {f.cad_pin} (multipolygon with >1 feature)')
                skipped += 1
                continue

            # Edge case: we sometimes have "zero area" geometries.
            if isinstance(f.shape.envelope, Point):
                LOGGER.info(f'Feature with PIN {f.cad_pin} has zero area')
                add.envelope = None
                add.boundary = None
                suspect += 1

            address_nice = ''  # Human-readable "nice" address.
            if f.cad_lot_number:
                add.data['lot_number'] = f.cad_lot_number
                address_nice += '(Lot {}) '.format(f.cad_lot_number)
            if f.cad_house_number:
                add.data['house_number'] = f.cad_house_number
                address_nice += '{} '.format(f.cad_house_number)
            if f.cad_road_name:
                add.data['road_name'] = f.cad_road_name
                address_nice += '{} '.format(f.cad_road_name)
                if f.cad_road_type:
                    add.data['road_type'] = f.cad_road_type
                    # Try to match an existing suffix.
                    if f.cad_road_type in ROADS_ABBREV:
                        address_nice += '{} '.format(ROADS_ABBREV[f.cad_road_type])
                    else:
                        address_nice += '{} '.format(f.cad_road_type)
            if f.cad_locality:
                add.data['locality'] = f.cad_locality
                address_nice += '{} '.format(f.cad_locality)
            if f.cad_postcode:
                add.data['postcode'] = f.cad_postcode
                address_nice += '{} '.format(int(f.cad_postcode))
            if f.cad_owner_name:
                add.owner = f.cad_owner_name
            if f.cad_ownership:
                add.data['ownership'] = f.cad_ownership
            if f.cad_pin:
                add.data['pin'] = f.cad_pin
            # Reserves
            if f.cad_pitype_3_1 and f.cad_pitype_3_1.startswith('R'):
                match = re.search(reserve_pattern, f.cad_pitype_3_1)
                if match:
                    add.data['reserve'] = match.group()
                    address_nice = 'Reserve {} '.format(match.group()) + address_nice

            add.address_nice = address_nice.strip()
            add.address_text = add.get_address_text()
            add.save()
            if update:
                updates += 1
            else:
                created += 1

    LOGGER.info(f'Created {created} addresses, updated {updates}, skipped {skipped}, suspect {suspect}')


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
