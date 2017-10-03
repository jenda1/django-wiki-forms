# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

# from django.utils.translation import ugettext as _
from django.views.generic.base import View
from django.utils.decorators import method_decorator
from wiki.views.mixins import ArticleMixin
from wiki.decorators import get_article
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import html
from wiki.core.markdown import ArticleMarkdown

from . import models
from . import utils
from . import tasks

import logging
import json
import ipdb

logger = logging.getLogger(__name__)

class InputDataView(ArticleMixin, LoginRequiredMixin, View):
    http_method_names = ['get', 'post', ]

    @method_decorator(get_article(can_read=True))
    def dispatch(self, request, article, *args, **kwargs):
        return super(InputDataView, self).dispatch(request, article, *args, **kwargs)

    def get(self, request, input_name, *args, **kwargs):
        if not self.article.can_read(request.user):
            return HttpResponse(status=403)

        q = models.Input.objects.filter(article=self.article, key=input_name)
        idef = models.InputDefinition.objects.filter(article=self.article, key=input_name).last()

        if 'all' in request.GET:
            out = dict({'titles': ['Username', input_name], 'values': list()})
            for o in q.values('owner', 'owner__username', 'owner__first_name', 'owner__last_name').order_by('owner__email').distinct():
                v = q.filter(owner=o['owner']).last()
                if v:
                    v_json = json.loads(v.val)
                    out['values'].append((o['owner__username'], html.escape(v_json)))
                elif idef:
                    tasks.evaluate_init(idef.pk, request.user.pk)

        else:
            v = q.filter(owner=request.user).last()
            if v:
                out = json.loads(v.val)
            else:
                if idef:
                    ipdb.set_trace()
                    tasks.evaluate_init(idef.pk, request.user.pk)

                return HttpResponse(status=204)

        return JsonResponse(out, safe=False)


    def post(self, request, input_name, *args, **kwargs):
        # FIXME: maybe a bit expensive check
        md = ArticleMarkdown(self.article, preview=True)
        md.convert(self.article.current_revision.content)

        if input_name not in md.inputextension_fields:
            return HttpResponse(status=500)

        req = request.body.decode('utf-8')
        try:
            data = json.loads(req)
            data_json = json.dumps(data)
        except:
            logger.warning('broken data received: {}'.format(
                req[:75] + '..' if len(req) > 75 else req))
            return HttpResponse(status=500)

        curr = models.Input.objects.filter(article=self.article, key=input_name).last()
        if curr and curr.val == data_json:
            return HttpResponse(status=204)

        obj = models.Input(article=self.article, owner=request.user, key=input_name, val=data_json)
        obj.full_clean()
        obj.save()

        return HttpResponse(status=204)
