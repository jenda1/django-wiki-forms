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

class InputDependencyAdmin(admin.ModelAdmin):
    list_display = ('pk', 'idef', 'article', 'name', 'per_user')
    list_filter = ('idef', 'article', 'name', 'per_user')

class DockerInline(admin.TabularInline):
    model = models.InputDocker


class InputDefValueAdmin(admin.ModelAdmin):
    list_display = ('pk', 'idef', 'owner', 'val')
    list_filter = ('idef', 'owner')
    inlines = [
            DockerInline,
            ]

class InputDockerAdmin(admin.ModelAdmin):
    list_display = ('pk', 'value', 'image', 'scenario', 'args', 'container_id')


admin.site.register(models.Input, InputAdmin)
admin.site.register(models.InputDefinition, InputDefinitionAdmin)
admin.site.register(models.InputDefValue, InputDefValueAdmin)
admin.site.register(models.InputDependency, InputDependencyAdmin)
admin.site.register(models.InputDocker, InputDockerAdmin)
