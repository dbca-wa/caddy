# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import djorm_pgfulltext.fields
import django.contrib.gis.db.models.fields
from shack.utils import LoadExtension


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Address',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('cadastre_id', models.CharField(unique=True, max_length=64, db_index=True)),
                ('address_text', models.TextField()),
                ('address_nice', models.TextField(null=True, blank=True)),
                ('centroid', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('search_index', djorm_pgfulltext.fields.VectorField()),
            ],
        ),
        LoadExtension('pg_trgm'),
    ]
