from __future__ import absolute_import, unicode_literals

from django.contrib import admin

from . import models


class InputAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'owner', 'name', 'created', 'newer_pk')
    list_filter = ('article', 'owner', 'name')

    def newer_pk(self, obj):
        return obj.newer.pk if obj.newer else "None"


class InputDefinitionAdmin(admin.ModelAdmin):
    list_display = ('pk', 'article', 'name')
    list_filter = ('article', 'name')


admin.site.register(models.Input, InputAdmin)
admin.site.register(models.InputDefinition, InputDefinitionAdmin)
