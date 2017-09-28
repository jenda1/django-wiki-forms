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

import logging
import json

from . import utils

logger = logging.getLogger(__name__)

class InputDataView(ArticleMixin, LoginRequiredMixin, View):
    http_method_names = ['get', 'post', ]

    @method_decorator(get_article(can_read=True))
    def dispatch(self, request, article, *args, **kwargs):
        return super(InputDataView, self).dispatch(request, article, *args, **kwargs)

    def get(self, request, input_name, *args, **kwargs):
        if not self.article.can_read(request.user):
            return HttpResponse(status=403)

        # FIXME: check the article has 'get-all' of the field
        # FIXME: add check that get-all is added to articles that author owns
        # if 'all' in request.GET and not self.article.can_write(request.user):
        #     return HttpResponse(status=403)

        q = models.Input.objects.filter(article=self.article, key=input_name)

        if 'all' in request.GET:
            out = dict({'titles': ['Username', input_name], 'values': list()})
            for o in q.values('owner', 'owner__username', 'owner__first_name', 'owner__last_name').order_by('owner__email').distinct():
                v = q.filter(owner=o['owner']).last()
                if v:
                    v_json = json.loads(v.val)
                    out['values'].append((o['owner__username'], html.escape(v_json)))
        else:
            out = q.filter(owner=request.user).last()
            if out:
                out = json.loads(out.val)
            else:
                utils.tryEval(self.article, input_name, request.user)

        return JsonResponse(out, safe=False) if out else HttpResponse(status=204)


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
