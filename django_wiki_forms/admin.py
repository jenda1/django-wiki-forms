from __future__ import absolute_import, unicode_literals

from django import forms
from django.contrib import admin

from . import models


class InputAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'owner', 'key', 'created')

class InputDefinitionAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'key')

admin.site.register(models.Input, InputAdmin)
admin.site.register(models.InputDefinition, InputDefinitionAdmin)
