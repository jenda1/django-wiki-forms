from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext as _
from wiki.core.plugins import registry
from wiki.core.plugins.base import BasePlugin
from . import settings, views
from .mdx.input import InputExtension
from .mdx.defs import DefExtension
from .mdx.display import DisplayExtension
from django.conf.urls import url

import ipdb  # NOQA

import logging
logger = logging.getLogger(__name__)



class InputsPlugin(BasePlugin):

    slug = settings.SLUG

    urlpatterns = {'article': [
        url(r'input/(?P<input_id>\d*)$', views.InputDataView.as_view(), name='forms-input'),
        url(r'display/(?P<display_id>\d*)$', views.DisplayDataView.as_view(), name='forms-display'),
    ]}

    sidebar = {'headline': _('Inputs'),
               'icon_class': 'fa-pencil-square-o',
               'template': 'wiki/plugins/forms/sidebar.html',
               'form_class': None,
               'get_form_kwargs': (lambda a: {})}

    class RenderMedia:
        js = [
            'wiki/js/dw-forms.js',
            'wiki/js/ws4redis.js',
            'wiki/js/jquery.ajaxQueue.js',
        ]

        css = {
            'all': 'wiki/css/dw-forms.css',
        }

    markdown_extensions = [InputExtension(), DisplayExtension(), DefExtension()]

    html_whitelist = ['input', 'textarea']
    html_attributes = {
        'input': ['data-id', 'class', 'id', 'type', 'disabled', 'multiple'],
        'textarea': ['data-id', 'class', 'id', 'type', 'disabled', 'multiple'],
        'span': ['data-id', 'data-listen', 'class', 'id'],
    }


registry.register(InputsPlugin)
