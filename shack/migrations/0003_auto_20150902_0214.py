# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shack', '0002_address_envelope'),
    ]

    operations = [
        migrations.RenameField(
            model_name='address',
            old_name='cadastre_id',
            new_name='object_id',
        ),
        migrations.RemoveField(
            model_name='address',
            name='search_index',
        ),
    ]
