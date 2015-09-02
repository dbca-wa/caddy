# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shack', '0004_auto_20150902_0222'),
    ]

    operations = [
        migrations.RunSQL('ALTER TABLE shack_address ADD COLUMN tsv tsvector;'),
        migrations.RunSQL('CREATE INDEX tsv_idx ON shack_address USING gin(tsv);'),
        migrations.RunSQL('''CREATE TRIGGER shack_address_tsv_update BEFORE INSERT OR UPDATE
ON shack_address FOR EACH ROW EXECUTE PROCEDURE
tsvector_update_trigger(tsv, 'pg_catalog.english', 'address_text');'''),
    ]
