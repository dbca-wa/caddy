# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shack', '0003_auto_20150902_0214'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='address_no',
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='address_sfx',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='locality',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='lot_no',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='postcode',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='reserve',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='road',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='road_sfx',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='strata',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='address',
            name='survey_lot',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='address',
            name='address_text',
            field=models.TextField(help_text=b'Address document for search'),
        ),
    ]
