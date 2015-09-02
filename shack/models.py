from django.contrib.gis.db import models
from django.utils.text import Truncator


class Address(models.Model):
    """An address indexed and searchable via PostgreSQL.
    """
    object_id = models.CharField(max_length=64, unique=True, db_index=True)
    address_text = models.TextField(help_text='Address document for search')
    address_nice = models.TextField(null=True, blank=True)
    centroid = models.PointField(srid=4326)
    envelope = models.PolygonField(srid=4326, null=True, blank=True)
    lot_no = models.CharField(max_length=64, null=True, blank=True)
    address_no = models.IntegerField(null=True, blank=True)
    address_sfx = models.CharField(max_length=64, null=True, blank=True)
    road = models.CharField(max_length=64, null=True, blank=True)
    road_sfx = models.CharField(max_length=64, null=True, blank=True)
    locality = models.CharField(max_length=64, null=True, blank=True)
    postcode = models.CharField(max_length=64, null=True, blank=True)
    survey_lot = models.CharField(max_length=256, null=True, blank=True)
    strata = models.CharField(max_length=256, null=True, blank=True)
    reserve = models.CharField(max_length=256, null=True, blank=True)

    def __unicode__(self):
        if self.address_nice:
            return Truncator(self.address_nice).words(15)
        else:
            return Truncator(self.address_text).words(15)
