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
    idef = models.InputDefinition.objects.get(pk=idef_pk)
    owner = User.objects.get(pk=owner_pk)
    logger.warning("evaluate {} (@{})".format(idef, owner))
    utils.evaluate_idef(idef, owner)


@shared_task
def evaluate_init(idef_pk, owner_pk):
    idef = models.InputDefinition.objects.get(pk=idef_pk)
    owner = User.objects.get(pk=owner_pk)
    logger.info("evaluate init {} (@{})".format(idef, owner))

    todo = [idef, ]
    done = list()

    while todo:
        i = todo.pop()
        done.append(i)

        if i.inputdependency_set.count() == 0:
            pass
        # evaluate.delay(i.pk, owner.pk)
        else:
            for dep in i.inputdependency_set.all():
                if dep.definition not in done:
                    todo.append(dep.definiton)
