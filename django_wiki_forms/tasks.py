from __future__ import absolute_import, unicode_literals

from celery import shared_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model

from . import models
from . import utils


User = get_user_model()
logger = get_task_logger(__name__)



@shared_task
def evaluate_idef(idef_pk, owner_pk):
    try:
        idef = models.InputDefinition.objects.get(pk=idef_pk)
    except models.InputDefinition.DoesNotExist:
        logger.warning("evaluate of unknown idef {}".format(idef_pk))
        return

    owner = User.objects.get(pk=owner_pk)
    logger.warning("evaluate {} (@{})".format(idef, owner))
    utils.evaluate_idef(idef, owner)
