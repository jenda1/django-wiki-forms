# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

# from django.utils.translation import ugettext as _
from django.views.generic.base import View
from django.utils.decorators import method_decorator
from wiki.views.mixins import ArticleMixin
from wiki.decorators import get_article
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from wiki.core.markdown import ArticleMarkdown
from wiki.models import Article
from django.shortcuts import render
from collections import defaultdict
# from . import models
# from . import tasks
from . import utils

import logging
import json
import re
import ipdb  # NOQA

logger = logging.getLogger(__name__)

NAME_RE = re.compile(
    r'^\s*(?P<name>[-\w]+?)(?P<arr>\[(?P<query>.+?)\])?\s*$',
    re.IGNORECASE
)

class InputDataView(ArticleMixin, LoginRequiredMixin, View):
    http_method_names = ['get', 'post', ]

    @method_decorator(get_article(can_read=True))
    def dispatch(self, request, article, *args, **kwargs):
        self.md = ArticleMarkdown(article, preview=True)
        self.md.convert(article.current_revision.content)

        return super(InputDataView, self).dispatch(request, article, *args, **kwargs)

    def get(self, request, input_id, *args, **kwargs):
        try:
            field = self.md.input_fields[int(input_id)-1]
            val = utils.get_input_val(self.article, field['name'], request.user)
        except Exception as e:
            logger.warning('broken get request: {}'.format(e))
            return HttpResponse(status=400)

        return JsonResponse({
            'val': val if val else "",
            'locked': self.article.current_revision.locked}, safe=False)


    def post(self, request, input_id, *args, **kwargs):
        if self.article.current_revision.locked:
            return HttpResponse(status=403)

        try:
            field = self.md.input_fields[int(input_id)-1]
            name = field['name']
            req = request.body.decode('utf-8')
            data = json.loads(req)

            if field['variant'] in ['number', 'number_inline']:
                data = int(data)

            data_json = json.dumps(data)
        except Exception as e:
            logger.warning('broken get request: {}'.format(e))
            return HttpResponse(status=500)

        utils.update_input(self.article, name, request.user, data_json)
        return HttpResponse(status=204)



class DisplayDataView(ArticleMixin, LoginRequiredMixin, View):
    http_method_names = ['get', ]

    @method_decorator(get_article(can_read=True))
    def dispatch(self, request, article, *args, **kwargs):
        self.md = ArticleMarkdown(article, preview=True)
        self.md.convert(article.current_revision.content)

        return super(DisplayDataView, self).dispatch(request, article, *args, **kwargs)


    def get(self, request, display_id, *args, **kwargs):  # NOQA
        try:
            i = self.md.display_fields[int(display_id)-1]
            variant = i['variant'] if i['variant'] else "list"
            fields = i['fields']
        except:
            logger.warning('broken get request')
            return HttpResponse(status=400)

        if variant in ['list']:
            data = list()

            for i, f in enumerate(fields):
                a = Article.objects.get(pk=f['article_pk'])

                val = utils.get_input_val(a, f['name'], request.user)
                if val:
                    data.append(val)

            c = dict(data=data)

        elif variant in ['files']:
            data = list()
            for i, f in enumerate(fields):
                a = self.article if f['article_pk'] == 'this' else Article.objects.get(pk=f['article_pk'])
                for v in utils.evaluate_field(a, f['name'], request.user):
                    data += v

            c = dict(data=data)

        elif variant == 'per-user':
            columns = list()
            data = defaultdict(lambda: [None] * len(fields))
            for x, f in enumerate(fields):
                columns.append(f['name'])

                v = utils.get_input_val(Article.objects.get(pk=f['article_pk']), f['name'], request.user)
                if v:
                    for user in v:
                        data[user][x] = v[user]

            c = dict(data=dict(data), columns=columns)
            print(c)

        else:
            c = dict()

        return render(request,
                      "wiki/plugins/forms/display-{}.html".format(variant),
                      context=c)
