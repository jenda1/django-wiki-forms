from __future__ import absolute_import, unicode_literals

import os
from django.utils.translation import ugettext as _
from wiki.core.plugins import registry
from wiki.core.plugins.base import BasePlugin
from . import settings, views
from .mdx.input import InputExtension
from .mdx.defs import DefExtension
from django.conf.urls import url

from celery import Celery



class InputsPlugin(BasePlugin):

    slug = settings.SLUG

    urlpatterns = {'article': [
        url(r'(?P<input_name>.*)$', views.InputDataView.as_view(), name='input_data'),
    ]}

    sidebar = {'headline': _('Inputs'),
               'icon_class': 'fa-pencil-square-o',
               'template': 'wiki/plugins/inputs/sidebar.html',
               'form_class': None,
               'get_form_kwargs': (lambda a: {})}

    class RenderMedia:
        js = [
            'wiki/plugins/forms/inputs.js',
            'wiki/js/jsrender.min.js',
        ]

        css = {
            'screen': 'wiki/css/inputs.css',
        }

    markdown_extensions = [InputExtension(), DefExtension()]

    html_whitelist = ['input', 'textarea']
    html_attributes = {
        'input': ['data-url', 'class', 'id', 'type', 'disabled', 'multiple'],
        'textarea': ['data-url', 'class', 'id', 'type', 'disabled', 'multiple'],
    }


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django-wiki.settings')

app = Celery('django-wiki')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

registry.register(InputsPlugin)
