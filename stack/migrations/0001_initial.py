# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Cadastre',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('object_id', models.CharField(unique=True, max_length=64, db_index=True)),
                ('address_nice', models.CharField(max_length=256)),
                ('centroid', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('envelope', django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ('lot_no', models.CharField(max_length=64, null=True, blank=True)),
                ('address_no', models.IntegerField(null=True, blank=True)),
                ('address_sfx', models.CharField(max_length=64, null=True, blank=True)),
                ('road', models.CharField(max_length=64, null=True, blank=True)),
                ('road_sfx', models.CharField(max_length=64, null=True, blank=True)),
                ('locality', models.CharField(max_length=64, null=True, blank=True)),
                ('postcode', models.CharField(max_length=64, null=True, blank=True)),
                ('survey_lot', models.CharField(max_length=256, null=True, blank=True)),
                ('strata', models.CharField(max_length=256, null=True, blank=True)),
                ('reserve', models.CharField(max_length=256, null=True, blank=True)),
            ],
        ),
    ]
