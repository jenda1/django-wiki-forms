from __future__ import absolute_import, unicode_literals

from django.contrib import admin

from . import models


class InputAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'owner', 'name', 'created')

class InputDefinitionAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'name')


admin.site.register(models.Input, InputAdmin)
admin.site.register(models.InputDefinition, InputDefinitionAdmin)
