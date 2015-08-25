from django.contrib.gis.db import models
from django.utils.text import Truncator
from djorm_pgfulltext.models import SearchManager
from djorm_pgfulltext.fields import VectorField


class Address(models.Model):
    cadastre_id = models.CharField(max_length=64, unique=True, db_index=True)
    address_text = models.TextField()
    address_nice = models.TextField(null=True, blank=True)
    centroid = models.PointField(srid=4326)
    envelope = models.PolygonField(srid=4326, null=True, blank=True)
    search_index = VectorField()

    objects = SearchManager(
        fields=('address_text', 'address_nice'), auto_update_search_field=True)

    def __unicode__(self):
        if self.address_nice:
            return Truncator(self.address_nice).words(15)
        else:
            return Truncator(self.address_text).words(15)
