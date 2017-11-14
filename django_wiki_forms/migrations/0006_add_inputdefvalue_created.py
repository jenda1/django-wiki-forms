# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-11-14 07:20
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('django_wiki_forms', '0005_add_docker'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='inputdependency',
            name='depend_idef',
        ),
        migrations.AddField(
            model_name='inputdefvalue',
            name='created',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='created'),
            preserve_default=False,
        ),
    ]
