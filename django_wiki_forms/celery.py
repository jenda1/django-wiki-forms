from celery import Celery

from django_wiki_forms import settings

app = Celery('django-wiki-forms')
app.config_from_object(settings)
app.autodiscover_tasks()
