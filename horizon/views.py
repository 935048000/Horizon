# coding=utf-8
# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django import shortcuts
from django import template
from django.utils import encoding
from django.views import generic

import horizon
from horizon import exceptions


class PageTitleMixin(object):
    """A mixin that renders out a page title into a view.

    Many views in horizon have a page title that would ordinarily be
    defined and passed through in get_context_data function, this often
    leads to a lot of duplicated work in each view.

    This mixin standardises the process of defining a page title, letting
    views simply define a variable that is rendered into the context for
    them.

    There are cases when page title in a view may also display some context
    data, for that purpose the page_title variable supports the django
    templating language and will be rendered using the context defined by the
    views get_context_data.

    将页面标题呈现为视图的mixin。

    在horizon中，许多视图都有一个页面标题，通常会在get_context_data函数中定义和传递，
    这通常会导致在每个视图中有很多重复的工作。

    这个mixin标准化过程定义了一个页面标题，让视图简单地定义一个变量，为它们提供了上下文。

    视图中的页面标题也可以显示一些上下文数据，为此，page_title变量支持django模板语言，
    并使用视图get_context_data定义的上下文呈现。
    """

    page_title = ""

    def render_context_with_title(self, context):
        """This function takes in a context dict and uses it to render the
        page_title variable, it then appends this title to the context using
        the 'page_title' key. If there is already a page_title key defined in
        context received then this function will do nothing.
        这个函数接受一个上下文命令，并使用它来呈现page_title变量，
        然后使用“page_title”键将这个标题附加到上下文。
        如果在接收到的上下文中定义了一个page_title键，
        那么这个函数将什么也不做。
        """

        if "page_title" not in context:
            con = template.Context(context)
            # NOTE(sambetts): Use force_text to ensure lazy translations
            # are handled correctly.
            # 注意(sambetts):使用force_text确保延迟翻译
            temp = template.Template(encoding.force_text(self.page_title))
            context["page_title"] = temp.render(con)
        return context

    def render_to_response(self, context):
        """This is an override of the default render_to_response function that
        exists in the django generic views, this is here to inject the
        page title into the context before the main template is rendered.
        这是默认render_to_response函数的覆盖
        在django泛型视图中，这里是注入
        在呈现主模板之前，将页面标题放入上下文。
        """

        context = self.render_context_with_title(context)
        return super(PageTitleMixin, self).render_to_response(context)


class HorizonTemplateView(PageTitleMixin, generic.TemplateView):
    pass


class HorizonFormView(PageTitleMixin, generic.FormView):
    pass


def user_home(request):
    """Reversible named view to direct a user to the appropriate homepage.
    可逆转的命名视图，将用户引导到适当的主页。"""
    return shortcuts.redirect(horizon.get_user_home(request.user))


class APIView(HorizonTemplateView):
    """A quick class-based view for putting API data into a template.
    一个基于类的快速视图，用于将API数据放入模板中。

    Subclasses must define one method, ``get_data``, and a template name
    via the ``template_name`` attribute on the class.

    Errors within the ``get_data`` function are automatically caught by
    the :func:`horizon.exceptions.handle` error handler if not otherwise
    caught.
    """

    def get_data(self, request, context, *args, **kwargs):
        """This method should handle any necessary API calls, update the
        context object, and return the context object at the end.
        该方法应该处理任何必要的API调用，更新
        上下文对象，并在最后返回上下文对象。
        """
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        try:
            context = self.get_data(request, context, *args, **kwargs)
        except Exception:
            exceptions.handle(request)
        return self.render_to_response(context)
