import logging
import os
import re
from tempfile import NamedTemporaryFile

import orjson
import requests
from azure.storage.blob import BlobClient
from django.conf import settings
from django.contrib.gis.geos import GEOSException, GEOSGeometry, MultiPolygon, Point, Polygon
from django.db import transaction
from django.db.migrations.operations.base import Operation
from fudgeo.geopkg import GeoPackage
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Address

LOGGER = logging.getLogger("caddy")

WFS_PAGE_SIZE = 1000
WFS_TIMEOUT = (10, 120)
RESERVE_PATTERN = re.compile(r"(?P<reserve>[0-9]+)$")
ADDRESS_UPDATE_FIELDS = (
    "centroid",
    "envelope",
    "boundary",
    "owner",
    "address_nice",
    "address_text",
    "data",
)


class LoadExtension(Operation):
    """Class to assist with loading PostgreSQL extension during migrations."""

    reversible = True

    def __init__(self, name):
        self.name = name

    def state_forwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute(f"CREATE EXTENSION IF NOT EXISTS {self.name}")

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        schema_editor.execute(f"DROP EXTENSION {self.name}")

    def describe(self):
        return f"Creates extension {self.name}"


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


def get_feature_count(session=None, timeout=WFS_TIMEOUT):
    """Return the number of features in the cadastre layer.

    This uses ``resultType=hits`` so the server only has to count matching
    features. Asking for a normal GetFeature response (even with
    ``maxFeatures=1``) still makes GeoServer evaluate the query, including any
    ``sortBy``, over the whole layer, which is slow enough on large layers to
    look like the harvest has hung.
    """
    geoserver_url = os.environ["GEOSERVER_URL"]
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": os.environ["CADASTRE_LAYER"],
        "resultType": "hits",
    }
    if session is None:
        session = requests
        auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASSWORD"])
    else:
        auth = None

    resp = session.get(url=geoserver_url, auth=auth, params=params, timeout=timeout)
    resp.raise_for_status()
    # Response is always XML. Just parse the feature count from the content.
    content = str(resp.content)
    pattern = r'numberOfFeatures="(?P<featureCount>\d+)"'
    results = re.findall(pattern, content)
    if not results:
        raise ValueError("WFS response did not contain a feature count")
    return int(results[0])


def _wfs_session(auth):
    """Return a requests session with connection reuse and retries for transient errors."""
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.auth = auth
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def harvest_cadastre_wfs(limit=None):
    """Query the cadastre WFS for features.

    ``limit`` is the optional maximum number of features to query. Returns a
    dictionary of created/updated/skipped/suspect counts.
    """
    if limit is not None:
        limit = int(limit)
        if limit < 0:
            raise ValueError("limit must be zero or greater")
        if limit == 0:
            LOGGER.info("Limit is 0; nothing to harvest")
            return {"created": 0, "updated": 0, "skipped": 0, "suspect": 0}

    geoserver_url = os.environ["GEOSERVER_URL"]
    auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASSWORD"])
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": os.environ["CADASTRE_LAYER"],
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "sortBy": "CAD_PIN",
    }
    summary = {"created": 0, "updated": 0, "skipped": 0, "suspect": 0}

    with _wfs_session(auth) as session:
        # Query once for the total feature count, then page through the results.
        # Use a hits query: it is much cheaper than a sorted GetFeature.
        LOGGER.info("Counting features in %s", params["typeName"])
        try:
            total_features = get_feature_count(session)
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("Could not determine feature count: %s", exc)
            total_features = -1

        if total_features == 0 and limit is None:
            LOGGER.info("Harvest complete: no features to process")
            return summary

        if total_features < 0:
            expected_total = limit
        elif limit is not None and limit < total_features:
            expected_total = limit
        else:
            expected_total = total_features

        start_index = 0
        previous_first_pin = None
        while True:
            if limit is not None:
                remaining = limit - start_index
                if remaining <= 0:
                    break
                params["maxFeatures"] = min(WFS_PAGE_SIZE, remaining)
            else:
                params["maxFeatures"] = WFS_PAGE_SIZE
            params["startIndex"] = start_index

            log_end = start_index + params["maxFeatures"]
            if expected_total is not None:
                log_end = min(log_end, expected_total)
            LOGGER.info(
                "Querying features %s to %s of %s",
                start_index,
                log_end,
                expected_total if expected_total is not None else "unknown",
            )

            response = session.get(geoserver_url, params=params, timeout=WFS_TIMEOUT)
            response.raise_for_status()
            features = orjson.loads(response.content).get("features") or []
            if not features:
                break

            # Guard against a server that ignores startIndex: without this the
            # loop would re-process the same page forever when the total count
            # is unknown.
            first_pin = (features[0].get("properties") or {}).get("CAD_PIN")
            if start_index and first_pin is not None and first_pin == previous_first_pin:
                LOGGER.error(
                    "WFS returned the same first feature for startIndex %s; stopping to avoid an endless loop",
                    start_index,
                )
                break
            previous_first_pin = first_pin

            if limit is not None:
                # Never process more than the requested number of features.
                features = features[: limit - start_index]

            page_skipped = 0
            page_suspect = 0
            page_features = []
            for feature in features:
                prop = feature.get("properties") or {}
                pin = prop.get("CAD_PIN")
                if pin is None or pin == "":
                    LOGGER.warning("Skipping feature without CAD_PIN")
                    page_skipped += 1
                    continue
                page_features.append((str(pin), prop, feature.get("geometry")))

            # Fetch all existing rows for this page in one query. in_bulk()
            # defaults to the primary key, but PINs are stored in object_id.
            existing = Address.objects.in_bulk(
                [pin for pin, _, _ in page_features],
                field_name="object_id",
            )
            processed = {}

            for pin, prop, geometry in page_features:
                if not geometry:
                    LOGGER.warning("Skipping feature with CAD_PIN %s (no geometry)", pin)
                    page_skipped += 1
                    continue

                try:
                    poly = GEOSGeometry(orjson.dumps(geometry))
                except (GEOSException, TypeError, ValueError) as exc:
                    LOGGER.warning("Skipping feature with CAD_PIN %s (invalid geometry: %s)", pin, exc)
                    page_skipped += 1
                    continue

                # Sometimes features are returned as MultiPolygon. If it contains
                # exactly one polygon, use that; otherwise skip the feature.
                if isinstance(poly, MultiPolygon):
                    if len(poly) != 1:
                        LOGGER.info(
                            "Skipping feature with CAD_PIN %s (multipolygon with %s polygons)",
                            pin,
                            len(poly),
                        )
                        page_skipped += 1
                        continue
                    poly = poly[0]

                if not isinstance(poly, Polygon) or poly.empty:
                    LOGGER.info(
                        "Skipping feature with CAD_PIN %s (unsupported or empty geometry: %s)",
                        pin,
                        poly.geom_type,
                    )
                    page_skipped += 1
                    continue

                try:
                    centroid = poly.centroid
                    envelope = poly.envelope
                    area = poly.area
                except GEOSException as exc:
                    LOGGER.warning("Skipping feature with CAD_PIN %s (invalid geometry: %s)", pin, exc)
                    page_skipped += 1
                    continue

                if centroid is None:
                    LOGGER.info("Skipping feature with CAD_PIN %s (no centroid)", pin)
                    page_skipped += 1
                    continue

                # Re-use the object if this PIN already appeared on this page.
                address = processed.get(pin) or existing.get(pin)
                if address is None:
                    address = Address(object_id=pin)
                processed[pin] = address
                address.data = {}

                address.centroid = centroid
                if area == 0:
                    # A zero-area geometry can have a line-like envelope, which
                    # cannot be stored in the PolygonField.
                    LOGGER.info("Feature with CAD_PIN %s has zero area", pin)
                    address.envelope = None
                    address.boundary = None
                    page_suspect += 1
                else:
                    address.envelope = envelope if isinstance(envelope, Polygon) else None
                    address.boundary = poly

                address_nice = ""  # Human-readable "nice" address.
                if prop.get("CAD_LOT_NUMBER"):
                    address.data["lot_number"] = prop["CAD_LOT_NUMBER"]
                    address_nice += "(Lot {}) ".format(prop["CAD_LOT_NUMBER"])
                if prop.get("CAD_HOUSE_NUMBER"):
                    address.data["house_number"] = prop["CAD_HOUSE_NUMBER"]
                    address_nice += "{} ".format(prop["CAD_HOUSE_NUMBER"])
                if prop.get("CAD_ROAD_NAME"):
                    address.data["road_name"] = prop["CAD_ROAD_NAME"]
                    address_nice += "{} ".format(prop["CAD_ROAD_NAME"])
                    if prop.get("CAD_ROAD_TYPE"):
                        address.data["road_type"] = prop["CAD_ROAD_TYPE"]
                        # Try to match an existing suffix.
                        if prop["CAD_ROAD_TYPE"] in ROADS_ABBREV:
                            address_nice += "{} ".format(ROADS_ABBREV[prop["CAD_ROAD_TYPE"]])
                        else:
                            address_nice += "{} ".format(prop["CAD_ROAD_TYPE"])
                if prop.get("CAD_LOCALITY"):
                    address.data["locality"] = prop["CAD_LOCALITY"]
                    address_nice += "{} ".format(prop["CAD_LOCALITY"])
                if prop.get("CAD_POSTCODE"):
                    address.data["postcode"] = prop["CAD_POSTCODE"]
                    address_nice += "{} ".format(prop["CAD_POSTCODE"])

                owner = prop.get("CAD_OWNER_NAME")
                address.owner = owner.strip() if isinstance(owner, str) else owner
                address.data["pin"] = pin

                # Reserves: match the SCDB importer by requiring an "R" prefix.
                pitype = prop.get("CAD_PITYPE_3_1")
                if isinstance(pitype, str) and pitype.startswith("R"):
                    match = RESERVE_PATTERN.search(pitype)
                    if match:
                        reserve_id = match.group("reserve")
                        address.data["reserve"] = reserve_id
                        address_nice = f"RESERVE {reserve_id} " + address_nice

                address.address_nice = address_nice.strip()
                address.address_text = address.get_address_text()

            to_create = [address for pin, address in processed.items() if pin not in existing]
            to_update = [address for pin, address in processed.items() if pin in existing]
            with transaction.atomic():
                if to_create:
                    # Upsert so a concurrent harvest can't trip the unique
                    # constraint between the in_bulk() lookup and this insert.
                    Address.objects.bulk_create(
                        to_create,
                        update_conflicts=True,
                        unique_fields=["object_id"],
                        update_fields=ADDRESS_UPDATE_FIELDS,
                    )
                if to_update:
                    Address.objects.bulk_update(to_update, ADDRESS_UPDATE_FIELDS)

            summary["created"] += len(to_create)
            summary["updated"] += len(to_update)
            summary["skipped"] += page_skipped
            summary["suspect"] += page_suspect

            start_index += len(features)
            LOGGER.info(
                "Processed %s features: created %s, updated %s, skipped %s, suspect %s",
                len(features),
                len(to_create),
                len(to_update),
                page_skipped,
                page_suspect,
            )

            if limit is not None and start_index >= limit:
                break
            if total_features >= 0 and start_index >= total_features:
                break

    LOGGER.info(
        "Harvest complete: created %s, updated %s, skipped %s, suspect %s",
        summary["created"],
        summary["updated"],
        summary["skipped"],
        summary["suspect"],
    )
    return summary


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
            LOGGER.info(f"Skipping feature with PIN {record['pin']} (multipolygon with >1 feature)")
            continue

        # Convert the fudgeo geometry to GEOSGeometry.
        poly = geom.polygons[0]
        shape = GEOSGeometry(memoryview(poly._to_wkb(bytearray())))

        address.centroid = shape.centroid
        address.envelope = shape.envelope
        address.boundary = shape

        # Edge case: we sometimes have "zero area" geometries.
        if isinstance(shape.envelope, Point):
            LOGGER.info(f"Feature with PIN {record['pin']} has zero area")
            address.envelope = None
            address.boundary = None
            suspect += 1

        address_nice = ""  # Human-readable "nice" address.

        if record["lot_number"]:
            address.data["lot_number"] = record["lot_number"]
            address_nice += f"(Lot {record['lot_number']}) "
        if record["house_number"]:
            address.data["house_number"] = record["house_number"]
            address_nice += f"{record['house_number']} "
        if record["road_name"]:
            address.data["road_name"] = record["road_name"]
            address_nice += f"{record['road_name']} "
            if record["road_type"]:
                address.data["road_type"] = record["road_type"]
                # Try to match an existing suffix.
                if record["road_type"] in ROADS_ABBREV:
                    address_nice += f"{ROADS_ABBREV[record['road_type']]} "
                else:
                    address_nice += f"{record['road_type']} "
        if record["locality"]:
            address.data["locality"] = record["locality"]
            address_nice += f"{record['locality']} "
        if record["postcode"]:
            address.data["postcode"] = record["postcode"]
            address_nice += f"{record['postcode']} "
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
