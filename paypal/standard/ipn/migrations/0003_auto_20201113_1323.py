# Generated by Django 3.1.3 on 2020-11-13 13:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ipn', '0002_auto_20201022_1204'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paypalipn',
            name='flag',
            field=models.BooleanField(blank=True, default=False),
        ),
        migrations.AlterField(
            model_name='paypalipn',
            name='test_ipn',
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
