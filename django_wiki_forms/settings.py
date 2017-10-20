from __future__ import absolute_import, unicode_literals

from django.conf import settings as django_settings

SLUG = 'forms'

INPUTS = getattr(
    django_settings,
    'WIKI_PLUGINS_INPUTS',
    ('text', 'text_inline',
     'hidden', 'hidden_inline',
     'number', 'number_inline',
     'file',
     'files',
     'textarea',
     ))

# CELERY
CELERY_BROKER_URL = getattr(django_settings, 'CELERY_BROKER_URL', None)
