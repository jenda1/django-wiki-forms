from __future__ import absolute_import, unicode_literals

from django.conf import settings as django_settings

SLUG = 'forms'

INPUTS = getattr(
    django_settings,
    'WIKI_PLUGINS_INPUTS',
    ('text', 'text_inline',
     'password', 'password_inline',
     'file',
     'files',
     'textarea',
     ))


BROKER_URL = getattr(django_settings, 'CELERY_BROKER_URL', None)
