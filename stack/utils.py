from django.contrib.gis.geos import GEOSGeometry
from django.core import management
import json
import logging
import os
import requests
from shack.utils import ROADS_ABBREV
from .models import Cadastre

logger = logging.getLogger('caddy')


def harvest_cadastre(limit=None):
    """Query the cadastre WFS for features. ``limit`` is optional integer of the
    maximum number of features to query.
    """
    geoserver_url = os.environ['GEOSERVER_URL']
    cadastre_layer = os.environ['CADASTRE_LAYER']
    url = '{}?service=WFS&version=1.1.0&request=GetFeature&typeName={}&outputFormat=application/json'.format(geoserver_url, cadastre_layer)
    auth = (os.environ['GEOSERVER_USER'], os.environ['GEOSERVER_PASSWORD'])
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
            if Cadastre.objects.filter(object_id=f['id']).exists():
                add = Cadastre.objects.get(object_id=f['id'])
                update = True  # Existing feature
            else:
                add = Cadastre(object_id=f['id'])
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
            create_features.append(add)
            if update:  # Save changes to existing features.
                add.save()
                updates += 1
        # Do a bulk_create for each iteration (new features only).
        Cadastre.objects.bulk_create(create_features)
        logger.info('Created {} addresses, updated {}'.format(len(create_features), updates))

    # Afterward, run the update_index management command.
    logger.info('Updating the haystack search_index')
    management.call_command('update_index', '--remove', '--workers=2')
    logger.info('Cadastre search_index update completed')
