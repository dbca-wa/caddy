from django.contrib.gis.geos import Point
from django.test import TestCase, Client
from mixer.backend.django import mixer
from webtest import TestApp

from geocoder import application
from shack.models import Address  # NOTE: don't use relative imports.


mixer.register(
    Address, centroid=lambda: Point(float(mixer.faker.latitude()), float(mixer.faker.longitude())),
)


class ShackTestCase(TestCase):
    client = Client()
    app = TestApp(application)

    def setUp(self):
        # Generate an Address object to test geocoding.
        self.address = mixer.blend(
            Address,
            object_id=1,
            address_nice='182 NORTHSTEAD ST SCARBOROUGH 6019',
            data={
                'survey_lot': 'LOT 442 ON PLAN 3697',
                'pin': 1,
                'postcode': '6019',
                'addrs_no': '182',
                'road_sfx': 'ST',
                'locality': 'SCARBOROUGH',
                'addrs_sfx': None,
                'road_name': 'NORTHSTEAD',
            }
        )
        self.address.address_text = self.address.get_address_text()
        self.address.save()

    def test_shack_str(self):
        self.assertTrue('SCARBOROUGH' in str(self.address))
        self.address.address_nice = None
        self.address.save()
        self.assertTrue('SCARBOROUGH' in str(self.address))

    def test_geocoder_app(self):
        resp = self.app.get('/')
        self.assertTrue(resp.status == '200 OK')

    def test_geocoder_api_pin(self):
        resp = self.app.get('/api/1')
        self.assertTrue(resp.status == '200 OK')

    def test_geocoder_api_geocode(self):
        resp = self.app.get('/api/geocode?q=scarborough')
        self.assertTrue(resp.status == '200 OK')
