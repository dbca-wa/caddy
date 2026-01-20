import logging
import os
import re
from tempfile import NamedTemporaryFile

import orjson
import requests
from azure.storage.blob import BlobClient
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from django.db.migrations.operations.base import Operation
from fudgeo.geopkg import GeoPackage

from .models import Address

LOGGER = logging.getLogger("caddy")


class LoadExtension(Operation):
    """Class to assist with loading PostgreSQL extension during migrations."""

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
        resp.append(
            {
                "object_id": address.object_id,
                "address": address.address_nice,
                "owner": address.owner,
                "lon": address.centroid.x,
                "lat": address.centroid.y,
            }
        )
    return resp


def get_feature_count():
    GEOSERVER_URL = os.environ["GEOSERVER_URL"]
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": os.environ["CADASTRE_LAYER"],
        "resultType": "hits",
    }
    auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASSWORD"])
    resp = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
    # Response is always XML. Just parse the feature count from the content.
    content = str(resp.content)
    pattern = r'numberOfFeatures="(?P<featureCount>\d+)"'
    results = re.findall(pattern, content)
    return int(results[0])


def harvest_cadastre_wfs(limit=None):
    """Query the cadastre WFS for features. ``limit`` is optional integer of the
    maximum number of features to query.
    """
    GEOSERVER_URL = os.environ["GEOSERVER_URL"]
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": os.environ["CADASTRE_LAYER"],
        "outputFormat": "application/json",
        "sortBy": "CAD_PIN",
        "maxFeatures": 1,
    }
    auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASSWORD"])
    # Initially query cadastre for the total feature count (maxfeatures=1)
    # Iterate over the total, 1000 features at a time.
    r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
    total_features = r.json()["totalFeatures"]
    if limit and limit < total_features:  # Optional limit on total features imported.
        total_features = limit
    params["maxFeatures"] = 1000
    if limit and limit < params["maxFeatures"]:
        params["maxFeatures"] = limit
    reserve_pattern = re.compile("(?P<reserve>[0-9]+)$")

    for i in range(0, total_features, params["maxFeatures"]):
        LOGGER.info(f"Querying features {i} to {i + params['maxFeatures']} of {total_features}")
        # Query the server for features, using startIndex.
        params["startIndex"] = i
        r = requests.get(url=GEOSERVER_URL, auth=auth, params=params)
        j = r.json()
        create_features = []
        updates = 0
        suspect = 0
        skipped = 0
        for f in j["features"]:
            #  Query for an existing feature (PIN == object_id)
            if Address.objects.filter(object_id=f["properties"]["CAD_PIN"]).exists():
                add = Address.objects.get(object_id=f["properties"]["CAD_PIN"])
                add.data = {}
                update = True  # Existing feature
            else:
                add = Address(object_id=f["properties"]["CAD_PIN"])
                update = False  # New feature
            poly = GEOSGeometry(orjson.dumps(f["geometry"]))
            # Edge case: sometimes features are returned as MultiPolygon.
            # If the feature is a MP containing one polygon feature, use that.
            # Otherwise, skip the feature entirely.
            if isinstance(poly, MultiPolygon) and len(poly) == 1:
                poly = poly[0]
            elif isinstance(poly, MultiPolygon) and len(poly) > 1:
                LOGGER.info(
                    f"Skipping feature with CAD_PIN {f['properties']['CAD_PIN']} (multipolygon with >1 feature)"
                )
                skipped += 1
                continue
            add.centroid = poly.centroid  # Precalculate the centroid.
            # Edge case: we've had some "zero area" geometries.
            if isinstance(poly.envelope, Point):
                LOGGER.info(
                    f"Feature with CAD_PIN {f['properties']['CAD_PIN']} has area of 0 (geometry: {f['geometry']})"
                )
                add.envelope = None
                suspect += 1
            else:
                add.envelope = poly.envelope  # Simplify the geometry bounds.
            prop = f["properties"]
            address_nice = ""  # Human-readable "nice" address.
            if "CAD_LOT_NUMBER" in prop and prop["CAD_LOT_NUMBER"]:
                add.data["lot_number"] = prop["CAD_LOT_NUMBER"]
                address_nice += "(Lot {}) ".format(prop["CAD_LOT_NUMBER"])
            if "CAD_HOUSE_NUMBER" in prop and prop["CAD_HOUSE_NUMBER"]:
                add.data["house_number"] = prop["CAD_HOUSE_NUMBER"]
                address_nice += "{} ".format(prop["CAD_HOUSE_NUMBER"])
            if "CAD_ROAD_NAME" in prop and prop["CAD_ROAD_NAME"]:
                add.data["road_name"] = prop["CAD_ROAD_NAME"]
                address_nice += "{} ".format(prop["CAD_ROAD_NAME"])
                if "CAD_ROAD_TYPE" in prop and prop["CAD_ROAD_TYPE"]:
                    add.data["road_type"] = prop["CAD_ROAD_TYPE"]
                    # Try to match an existing suffix.
                    if prop["CAD_ROAD_TYPE"] in ROADS_ABBREV:
                        address_nice += "{} ".format(ROADS_ABBREV[prop["CAD_ROAD_TYPE"]])
                    else:
                        address_nice += "{} ".format(prop["CAD_ROAD_TYPE"])
            if "CAD_LOCALITY" in prop and prop["CAD_LOCALITY"]:
                add.data["locality"] = prop["CAD_LOCALITY"]
                address_nice += "{} ".format(prop["CAD_LOCALITY"])
            if "CAD_POSTCODE" in prop and prop["CAD_POSTCODE"]:
                add.data["postcode"] = prop["CAD_POSTCODE"]
                address_nice += "{} ".format(prop["CAD_POSTCODE"])
            if "CAD_OWNER_NAME" in prop and prop["CAD_OWNER_NAME"]:
                add.owner = prop["CAD_OWNER_NAME"]
            if "CAD_PIN" in prop and prop["CAD_PIN"]:
                add.data["pin"] = prop["CAD_PIN"]

            # Reserves
            if "CAD_PITYPE_3_1" in prop and prop["CAD_PITYPE_3_1"]:
                m = re.search(reserve_pattern, prop["CAD_PITYPE_3_1"])
                if m:
                    add.data["reserve"] = m.group()
                    add.address_nice = f"RESERVE {m.group()} " + address_nice

            add.address_nice = address_nice.strip()
            add.address_text = add.get_address_text()
            if update:  # Save changes to existing features.
                add.save()
                updates += 1
            else:
                create_features.append(add)

        # Do a bulk_create for each iteration (new features only).
        Address.objects.bulk_create(create_features)
        LOGGER.info(
            f"Created {len(create_features)} addresses, updated {updates}, skipped {skipped}, suspect {suspect}"
        )


# Schema: https://kaartdijin-boodja.dbca.wa.gov.au/catalogue/entries/54/attribute/
CPT_CADASTRE_SCDB_SCHEMA = (
    "objectid",
    "geom",
    "pin",
    "usage_codes",
    "calc_area",
    "cent_latitude",
    "cent_longitude",
    "unit_type",
    "level_type",
    "level_number",
    "address_si",
    "lot_number",
    "land_type",
    "house_number",
    "road_name",
    "road_type",
    "road_suffix",
    "locality",
    "pc",
    "pitype_1",
    "pitype_2",
    "pitype_3_1",
    "pitype_3_2",
    "land_name",
    "reg_number",
    "reg_number_formatted",
    "owner_name",
    "owner_count",
    "sale_date",
    "doc_number",
    "gprpfx",
    "gprsfx",
    "strata",
    "ownership",
    "legend",
    "unit_number",
    "postcode",
    "length",
    "area",
)


def import_cpt_cadastre_scdb(blob_name=None):
    """Function to import CPT_CADASTRE_SCDB.gpkg from blob store."""
    if not blob_name:
        return

    # Download the Cadastre blob locally to a temporary file.
    blob = BlobClient(
        account_url=f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net",
        credential=settings.AZURE_ACCOUNT_KEY,
        container_name=settings.AZURE_CONTAINER,
        blob_name=blob_name,
    )
    LOGGER.info(f"Downloading {blob_name} from blob store")
    blob_local = NamedTemporaryFile()
    data = blob.download_blob()
    data.readinto(blob_local)
    blob_local.flush()
    LOGGER.info("Download complete")

    gpkg = GeoPackage(blob_local.name)
    # gpkg.connection opens a sqlite3 connection to the GPKG database.
    cursor = gpkg.connection.execute("SELECT COUNT(*) FROM CPT_CADASTRE_SCDB")
    count = cursor.fetchone()
    LOGGER.info(f"Importing {count[0]} cadastre records")

    count = 0
    created = 0
    updates = 0
    suspect = 0
    skipped = 0
    reserve_pattern = re.compile("(?P<reserve>[0-9]+)$")

    # Iterate over the database records.
    for row in gpkg.connection.execute("SELECT * FROM CPT_CADASTRE_SCDB"):
        count += 1
        record = dict(zip(CPT_CADASTRE_SCDB_SCHEMA, row))

        #  Query for an existing feature (PIN == object_id)
        if Address.objects.filter(object_id=record["pin"]).exists():
            address = Address.objects.get(object_id=record["pin"])
            address.data = {}
            update = True  # Existing feature
        else:
            address = Address(object_id=record["pin"])
            update = False  # New feature

        # Sometimes geometry contains >1 Polygon.
        # If >1 or 0, skip the feature.
        geom = record["geom"]
        if len(geom.polygons) > 1:
            LOGGER.info(f'Skipping feature with PIN {record["pin"]} (multipolygon with >1 feature)')
            continue

        # Convert the fudgeo geometry to GEOSGeometry.
        poly = geom.polygons[0]
        shape = GEOSGeometry(memoryview(poly._to_wkb(bytearray())))

        address.centroid = shape.centroid
        address.envelope = shape.envelope
        address.boundary = shape

        # Edge case: we sometimes have "zero area" geometries.
        if isinstance(shape.envelope, Point):
            LOGGER.info(f'Feature with PIN {record["pin"]} has zero area')
            address.envelope = None
            address.boundary = None
            suspect += 1

        address_nice = ""  # Human-readable "nice" address.

        if record["lot_number"]:
            address.data["lot_number"] = record["lot_number"]
            address_nice += f'(Lot {record["lot_number"]}) '
        if record["house_number"]:
            address.data["house_number"] = record["house_number"]
            address_nice += f'{record["house_number"]} '
        if record["road_name"]:
            address.data["road_name"] = record["road_name"]
            address_nice += f'{record["road_name"]} '
            if record["road_type"]:
                address.data["road_type"] = record["road_type"]
                # Try to match an existing suffix.
                if record["road_type"] in ROADS_ABBREV:
                    address_nice += f'{ROADS_ABBREV[record["road_type"]]} '
                else:
                    address_nice += f'{record["road_type"]} '
        if record["locality"]:
            address.data["locality"] = record["locality"]
            address_nice += f'{record["locality"]} '
        if record["postcode"]:
            address.data["postcode"] = record["postcode"]
            address_nice += f'{record["postcode"]} '
        if record["owner_name"]:
            address.owner = record["owner_name"].strip()
        if record["pin"]:
            address.pin = record["pin"]

        # Reserves
        if record["pitype_3_1"] and record["pitype_3_1"].startswith("R"):
            match = re.search(reserve_pattern, record["pitype_3_1"])
            if match:
                address.data["reserve"] = match.group()
                address_nice = f"RESERVE {match.group()} " + address_nice

        address.address_nice = address_nice.strip()
        address.address_text = address.get_address_text()
        address.save()

        if update:
            updates += 1
        else:
            created += 1

        # Running total:
        if count % 1000 == 0:
            LOGGER.info(f"Processed {count} addresses")

    LOGGER.info(f"Created {created} addresses, updated {updates}, skipped {skipped}, suspect {suspect}")


# Source: http://www.ipaustralia.gov.au/about-us/doing-business-with-us/address-standards/
ROADS_ABBREV = {
    "ACCS": "ACCESS",
    "ALLY": "ALLEY",
    "ALWY": "ALLEYWAY",
    "AMBL": "AMBLE",
    "ANCG": "ANCHORAGE",
    "APP": "APPROACH",
    "ARC": "ARCADE",
    "ART": "ARTERY",
    "AV": "AVENUE",
    "AVE": "AVENUE",
    "BASN": "BASIN",
    "BCH": "BEACH",
    "BLK": "BLOCK",
    "BVD": "BOULEVARD",
    "BR": "BRANCH",
    "BRCE": "BRACE",
    "BRK": "BREAK",
    "BDGE": "BRIDGE",
    "BDWY": "BROADWAY",
    "BYPA": "BYPASS",
    "BYWY": "BYWAY",
    "CAUS": "CAUSEWAY",
    "CTR": "CENTRE",
    "CNWY": "CENTREWAY",
    "CH": "CHASE",
    "CIR": "CIRCLE",
    "CLT": "CIRCLET",
    "CCT": "CIRCUIT",
    "CRCS": "CIRCUS",
    "CL": "CLOSE",
    "CLDE": "COLONNADE",
    "CMMN": "COMMON",
    "CON": "CONCOURSE",
    "CPS": "COPSE",
    "CNR": "CORNER",
    "CSO": "CORSO",
    "CT": "COURT",
    "CTYD": "COURTYARD",
    "CR": "CRESCENT",
    "CRES": "CRESCENT",
    "CRST": "CREST",
    "CRSS": "CROSS",
    "CRSG": "CROSSING",
    "CRD": "CROSSROAD",
    "COWY": "CROSSWAY",
    "CUWY": "CRUISEWAY",
    "CDS": "CUL-DE-SAC",
    "CTTG": "CUTTING",
    "DEVN": "DEVIATION",
    "DSTR": "DISTRIBUTOR",
    "DR": "DRIVE",
    "DRWY": "DRIVEWAY",
    "ELB": "ELBOW",
    "ENT": "ENTRANCE",
    "ESP": "ESPLANADE",
    "EST": "ESTATE",
    "EXP": "EXPRESSWAY",
    "EXTN": "EXTENSION",
    "FAWY": "FAIRWAY",
    "FTRK": "FIRE TRACK",
    "FITR": "FIRETRAIL",
    "FOLW": "FOLLOW",
    "FTWY": "FOOTWAY",
    "FSHR": "FORESHORE",
    "FORM": "FORMATION",
    "FWY": "FREEWAY",
    "FRNT": "FRONT",
    "FRTG": "FRONTAGE",
    "GDN": "GARDEN",
    "GDNS": "GARDENS",
    "GTE": "GATE",
    "GTES": "GATES",
    "GLD": "GLADE",
    "GLDE": "GLADE",
    "GRA": "GRANGE",
    "GRN": "GREEN",
    "GRND": "GROUND",
    "GR": "GROVE",
    "GLY": "GULLY",
    "HTS": "HEIGHTS",
    "HRD": "HIGHROAD",
    "HWY": "HIGHWAY",
    "INTG": "INTERCHANGE",
    "INTN": "INTERSECTION",
    "JNC": "JUNCTION",
    "LDG": "LANDING",
    "LNWY": "LANEWAY",
    "LEES": "LEES",
    "LT": "LITTLE",
    "LKT": "LOOKOUT",
    "LWR": "LOWER",
    "MNDR": "MEANDER",
    "MWY": "MOTORWAY",
    "MT": "MOUNT",
    "OTLK": "OUTLOOK",
    "PDE": "PARADE",
    "PKLD": "PARKLANDS",
    "PWY": "PARKWAY",
    "PKWY": "PARKWAY",
    "PHWY": "PATHWAY",
    "PIAZ": "PIAZZA",
    "PL": "PLACE",
    "PLAT": "PLATEAU",
    "PLZA": "PLAZA",
    "PKT": "POCKET",
    "PNT": "POINT",
    "PROM": "PROMENADE",
    "QDGL": "QUADRANGLE",
    "QDRT": "QUADRANT",
    "QY": "QUAY",
    "QYS": "QUAYS",
    "RMBL": "RAMBLE",
    "RAMP": "RAMP",
    "RNGE": "RANGE",
    "RCH": "REACH",
    "RES": "RESERVE",
    "RTT": "RETREAT",
    "RDGE": "RIDGE",
    "RGWY": "RIDGEWAY",
    "ROWY": "RIGHT OF WAY",
    "RVR": "RIVER",
    "RVWY": "RIVERWAY",
    "RVRA": "RIVIERA",
    "RD": "ROAD",
    "RDS": "ROADS",
    "RDSD": "ROADSIDE",
    "RDWY": "ROADWAY",
    "RNDE": "RONDE",
    "RSBL": "ROSEBOWL",
    "RTY": "ROTARY",
    "RND": "ROUND",
    "RTE": "ROUTE",
    "SWY": "SERVICE WAY",
    "SDNG": "SIDING",
    "SLPE": "SLOPE",
    "SND": "SOUND",
    "SQ": "SQUARE",
    "STRS": "STAIRS",
    "SHWY": "STATE HIGHWAY",
    "STPS": "STEPS",
    "STRA": "STRAND",
    "ST": "STREET",
    "STRP": "STRIP",
    "SBWY": "SUBWAY",
    "TCE": "TERRACE",
    "THOR": "THOROUGHFARE",
    "TLWY": "TOLLWAY",
    "TWRS": "TOWERS",
    "TRK": "TRACK",
    "TRL": "TRAIL",
    "TRLR": "TRAILER",
    "TRI": "TRIANGLE",
    "TKWY": "TRUNKWAY",
    "UPAS": "UNDERPASS",
    "UPR": "UPPER",
    "VDCT": "VIADUCT",
    "VLLS": "VILLAS",
    "VSTA": "VISTA",
    "WKWY": "WALKWAY",
    "WHRF": "WHARF",
    "WYND": "WYND",
}
