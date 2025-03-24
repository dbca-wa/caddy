from django.contrib.gis.geos import Point
from django.test import TransactionTestCase
from mixer.backend.django import mixer
from webtest import TestApp

from geocoder import application
from shack.models import Address

mixer.register(
    Address,
    centroid=lambda: Point(float(mixer.faker.latitude()), float(mixer.faker.longitude())),
)

TESTAPP = TestApp(application)


class GeocoderTestCase(TransactionTestCase):
    """A class for unit testing the geocoder application. Note that this class is intended
    to be used with the Django test runner in order to manage the test database.
    """

    def setUp(self):
        # Generate an Address object to test geocoding.
        self.address = mixer.blend(
            Address,
            object_id=1,
            address_nice="(Lot 442) 182 NORTHSTEAD ST SCARBOROUGH 6019",
            centroid="POINT(115.77111018362386 -31.897899253237053)",
            envelope="POLYGON((115.77102292300003 -31.89798640099997,115.77119745000005 -31.89798640099997,115.77119745000005 -31.897812103999968,115.77102292300003 -31.897812103999968,115.77102292300003 -31.89798640099997))",
            boundary="POLYGON((115.77102292300003 -31.89798640099997,115.77102437400004 -31.897812298999952,115.7710375040001 -31.897812280999972,115.77111097400007 -31.897812192999936,115.77119745000005 -31.897812103999968,115.77119598200011 -31.897986223999965,115.77102292300003 -31.89798640099997))",
            data={
                "survey_lot": "LOT 442 ON PLAN 3697",
                "pin": 1,
                "postcode": "6019",
                "addrs_no": "182",
                "road_sfx": "ST",
                "locality": "SCARBOROUGH",
                "addrs_sfx": None,
                "road_name": "NORTHSTEAD",
            },
        )
        self.address.address_text = self.address.get_address_text()
        self.address.save()

    def test_geocoder_home(self):
        """Test the home view responds."""
        response = TESTAPP.get("/", expect_errors=True)
        self.assertEqual(200, response.status_int)

    def test_geocoder_api_object_id(self):
        """Test that the address object URL returns JSON"""
        response = TESTAPP.get(f"/api/{self.address.object_id}", expect_errors=True)
        self.assertEqual(200, response.status_int)
        self.assertEqual(response.content_type, "application/json")
        self.assertTrue(self.address.address_text in response.testbody)

    def test_geocoder_api_geocode_point(self):
        """Test that the geocode path returns a result for a point intersect request"""
        response = TESTAPP.get(
            f"/api/geocode?point={self.address.centroid.x},{self.address.centroid.y}", expect_errors=True
        )
        self.assertEqual(200, response.status_int)
        self.assertEqual(response.content_type, "application/json")
        self.assertTrue(self.address.address_text in response.testbody)

    def test_geocoder_api_geocode_q(self):
        """Test that the geocode path returns a result for an address text request"""
        response = TESTAPP.get("/api/geocode?q=scarborough", expect_errors=True)
        self.assertEqual(200, response.status_int)
        self.assertEqual(response.content_type, "application/json")
        self.assertTrue(self.address.address_text in response.testbody)

    def test_geocoder_api_geocode_q_null(self):
        """Test that the geocode path returns no result for a non-existent address text request"""
        response = TESTAPP.get("/api/geocode?q=foobar", expect_errors=True)
        self.assertEqual(200, response.status_int)
        self.assertEqual(response.content_type, "application/json")
        self.assertTrue(self.address.address_text not in response.testbody)
