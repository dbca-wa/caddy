from django.contrib.gis.db import models
from django.template import Context, Template
from django.utils.text import Truncator


class Address(models.Model):
    """An address indexed and searchable via PostgreSQL.
    """
    object_id = models.CharField(max_length=64, unique=True, db_index=True)
    address_text = models.TextField(help_text='Address document for search')
    address_nice = models.TextField(null=True, blank=True)
    owner = models.TextField(null=True, blank=True)
    centroid = models.PointField(srid=4326)
    envelope = models.PolygonField(srid=4326, null=True, blank=True)
    data = models.JSONField(default=dict)

    def __str__(self):
        if self.address_nice:
            return Truncator(self.address_nice).words(15)
        else:
            return Truncator(self.address_text).words(15)

    def get_address_text(self):
        # Render the address_text field value from a template.
        f = """{{ object.address_nice }}
{% if object.owner %}{{ object.owner }}{% endif %}"""
        template = Template(f)
        context = Context({'object': self})
        return template.render(context).strip()
