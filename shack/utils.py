# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import
from django.contrib.gis.geos import GEOSGeometry
from django.core import management
from django.db.migrations.operations.base import Operation
import json
import logging
import os
import re
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
    # Initially query cadastre for the total features (maxFeatures=1)
    # Iterate over the total, 10000 features at a time.
    r = requests.get(url=url + '&maxFeatures=1', auth=auth)
    total_features = r.json()['totalFeatures']
    if limit and limit < total_features:  # Optional limit on total features imported.
        total_features = limit
    for i in range(0, total_features, 10000):
        print('Querying features {} to {}'.format(i, i+9999))
        # Query the server for features, using startIndex.
        q = url + '&maxFeatures=10000&startIndex={}'.format(i)
        r = requests.get(url=q, auth=auth)
        j = r.json()
        create_features = []
        updates = 0
        for f in j['features']:
            #  Query for an existing feature (id == cadastre_id)
            if Address.objects.filter(cadastre_id=f['id']).exists():
                add = Address.objects.get(cadastre_id=f['id'])
                update = True  # Existing feature
            else:
                add = Address(cadastre_id=f['id'])
                update = False  # New feature
            poly = GEOSGeometry(json.dumps(f['geometry']))
            add.centroid = poly.centroid  # Precalculate the centroid.
            add.envelope = poly.envelope  # Simplify the geometry bounds.
            # NOTE: not all fields might be present in the feature properties.
            prop = f['properties']
            # Strip out defined k, v pairs from the feature.
            remove = [
                'addrs_type', 'area_deriv', 'calc_area', 'cent_east', 'cent_lat',
                'cent_long', 'cent_zone', 'date_creat', 'date_modif',
                'legal_area', 'objectid', 'pin', 'reg_date', 'render',
                'render_label', 'scale']
            for k in remove:
                if k in prop:
                    prop.pop(k)
            # Get a list of not-None property values (strings).
            prop_values = [str(i) for i in prop.itervalues() if i]
            address_text = ' '.join(prop_values)  # Join these into the address field.
            add.address_text = re.sub(' +', ' ', address_text)  # Remove multiple spaces.
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
                    logger.info('Unknown road suffix: {}'.format(prop['road_sfx']))
            if 'locality' in prop and prop['locality']:
                address_nice += '{} '.format(prop['locality'])
            if 'postcode' in prop and prop['postcode']:
                address_nice += '{} '.format(prop['postcode'])
            if 'survey_lot' in prop and prop['survey_lot']:
                address_nice += '{} '.format(prop['survey_lot'])
            if 'strata' in prop and prop['strata']:
                address_nice += '{} '.format(prop['strata'])
            if 'reserve' in prop and prop['reserve']:
                address_nice += '{} '.format(prop['reserve'])
            add.address_nice = address_nice.strip()

            if not update and add.address_text:  # Only create a new Address with a not-null address.
                create_features.append(add)
            if update:  # Save changes to existing features.
                add.save()
                updates += 1
        # Do a bulk_create for each iteration (new features only).
        Address.objects.bulk_create(create_features)
        print('Created {} addresses, updated {}'.format(len(create_features), updates))

    # After, run the update_search_field management command.
    print('Updating the search_field index')
    management.call_command('update_search_field', 'shack')


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
    'BEND': 'BEND',
    'BLK': 'BLOCK',
    'BVD': 'BOULEVARD',
    'BR': 'BRANCH',
    'BRCE': 'BRACE',
    'BRAE': 'BRAE',
    'BRK': 'BREAK',
    'BDGE': 'BRIDGE',
    'BDWY': 'BROADWAY',
    'BROW': 'BROW',
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
    'COVE': 'COVE',
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
    'DALE': 'DALE',
    'DELL': 'DELL',
    'DEVN': 'DEVIATION',
    'DIP': 'DIP',
    'DSTR': 'DISTRIBUTOR',
    'DR': 'DRIVE',
    'DRWY': 'DRIVEWAY',
    'EDGE': 'EDGE',
    'ELB': 'ELBOW',
    'END': 'END',
    'ENT': 'ENTRANCE',
    'ESP': 'ESPLANADE',
    'EST': 'ESTATE',
    'EXP': 'EXPRESSWAY',
    'EXTN': 'EXTENSION',
    'FAWY': 'FAIRWAY',
    'FTRK': 'FIRE TRACK',
    'FITR': 'FIRETRAIL',
    'FLAT': 'FLAT',
    'FOLW': 'FOLLOW',
    'FTWY': 'FOOTWAY',
    'FSHR': 'FORESHORE',
    'FORM': 'FORMATION',
    'FWY': 'FREEWAY',
    'FRNT': 'FRONT',
    'FRTG': 'FRONTAGE',
    'GAP': 'GAP',
    'GDN': 'GARDEN',
    'GDNS': 'GARDENS',
    'GTE': 'GATE',
    'GTES': 'GATES',
    'GLD': 'GLADE',
    'GLDE': 'GLADE',
    'GLEN': 'GLEN',
    'GRA': 'GRANGE',
    'GRN': 'GREEN',
    'GRND': 'GROUND',
    'GR': 'GROVE',
    'GLY': 'GULLY',
    'HTS': 'HEIGHTS',
    'HRD': 'HIGHROAD',
    'HWY': 'HIGHWAY',
    'HILL': 'HILL',
    'INTG': 'INTERCHANGE',
    'INTN': 'INTERSECTION',
    'JNC': 'JUNCTION',
    'KEY': 'KEY',
    'LDG': 'LANDING',
    'LANE': 'LANE',
    'LNWY': 'LANEWAY',
    'LEES': 'LEES',
    'LINE': 'LINE',
    'LINK': 'LINK',
    'LT': 'LITTLE',
    'LKT': 'LOOKOUT',
    'LOOP': 'LOOP',
    'LWR': 'LOWER',
    'MALL': 'MALL',
    'MNDR': 'MEANDER',
    'MEW': 'MEW',
    'MEWS': 'MEWS',
    'MWY': 'MOTORWAY',
    'MT': 'MOUNT',
    'NOOK': 'NOOK',
    'OTLK': 'OUTLOOK',
    'PDE': 'PARADE',
    'PARK': 'PARK',
    'PKLD': 'PARKLANDS',
    'PWY': 'PARKWAY',
    'PKWY': 'PARKWAY',
    'PART': 'PART',
    'PASS': 'PASS',
    'PATH': 'PATH',
    'PHWY': 'PATHWAY',
    'PIAZ': 'PIAZZA',
    'PL': 'PLACE',
    'PLAT': 'PLATEAU',
    'PLZA': 'PLAZA',
    'PKT': 'POCKET',
    'PNT': 'POINT',
    'PORT': 'PORT',
    'PROM': 'PROMENADE',
    'QUAD': 'QUAD',
    'QDGL': 'QUADRANGLE',
    'QDRT': 'QUADRANT',
    'QY': 'QUAY',
    'QYS': 'QUAYS',
    'RMBL': 'RAMBLE',
    'RAMP': 'RAMP',
    'RNGE': 'RANGE',
    'RCH': 'REACH',
    'RES': 'RESERVE',
    'REST': 'REST',
    'RTT': 'RETREAT',
    'RIDE': 'RIDE',
    'RDGE': 'RIDGE',
    'RGWY': 'RIDGEWAY',
    'ROWY': 'RIGHT OF WAY',
    'RING': 'RING',
    'RISE': 'RISE',
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
    'ROW': 'ROW',
    'RUE': 'RUE',
    'RUN': 'RUN',
    'SWY': 'SERVICE WAY',
    'SDNG': 'SIDING',
    'SLPE': 'SLOPE',
    'SND': 'SOUND',
    'SPUR': 'SPUR',
    'SQ': 'SQUARE',
    'STRS': 'STAIRS',
    'SHWY': 'STATE HIGHWAY',
    'STPS': 'STEPS',
    'STRA': 'STRAND',
    'ST': 'STREET',
    'STRP': 'STRIP',
    'SBWY': 'SUBWAY',
    'TARN': 'TARN',
    'TCE': 'TERRACE',
    'THOR': 'THOROUGHFARE',
    'TLWY': 'TOLLWAY',
    'TOP': 'TOP',
    'TOR': 'TOR',
    'TWRS': 'TOWERS',
    'TRK': 'TRACK',
    'TRL': 'TRAIL',
    'TRLR': 'TRAILER',
    'TRI': 'TRIANGLE',
    'TKWY': 'TRUNKWAY',
    'TURN': 'TURN',
    'UPAS': 'UNDERPASS',
    'UPR': 'UPPER',
    'VALE': 'VALE',
    'VDCT': 'VIADUCT',
    'VIEW': 'VIEW',
    'VLLS': 'VILLAS',
    'VSTA': 'VISTA',
    'WADE': 'WADE',
    'WALK': 'WALK',
    'WKWY': 'WALKWAY',
    'WAY': 'WAY',
    'WHRF': 'WHARF',
    'WYND': 'WYND',
    'YARD': 'YARD'
}
