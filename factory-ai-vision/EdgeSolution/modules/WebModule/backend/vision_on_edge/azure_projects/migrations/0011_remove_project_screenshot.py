# Generated by Django 3.0.8 on 2021-08-26 05:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('azure_projects', '0010_auto_20210825_1021'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='screenshot',
        ),
    ]