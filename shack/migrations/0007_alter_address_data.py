# Generated by Django 3.2.3 on 2021-05-25 04:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shack', '0006_auto_20190507_1045'),
    ]

    operations = [
        migrations.AlterField(
            model_name='address',
            name='data',
            field=models.JSONField(default=dict),
        ),
    ]
