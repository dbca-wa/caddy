# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from shack.utils import CreateGinIndex


class Migration(migrations.Migration):

    dependencies = [
        ('shack', '0002_address_envelope'),
    ]

    operations = [
        CreateGinIndex(
            idx_name="shack_address_search_index_tsv",
            table="shack_address",
            field="address_nice || ' ' || address_text"
        )
    ]
