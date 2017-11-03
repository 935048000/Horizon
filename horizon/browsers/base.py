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

from django import template
from django.utils.translation import ugettext_lazy as _

from horizon.browsers.breadcrumb import Breadcrumb  # noqa
from horizon.tables import DataTable  # noqa
from horizon.utils import html


class ResourceBrowser(html.HTMLElement):
    """A class which defines a browser for displaying data.
        定义显示数据的浏览器的类。

    .. attribute:: name

        A short name or slug for the browser.
        用于浏览器的短名称或段塞。

    .. attribute:: verbose_name

        A more verbose name for the browser meant for display purposes.
        浏览器的一个更详细的名称用于显示目的。

    .. attribute:: navigation_table_class

        This table displays data on the left side of the browser.
        Set the ``navigation_table_class`` attribute with
        the desired :class:`~horizon.tables.DataTable` class.
        This table class must set browser_table attribute in Meta to
        ``"navigation"``.
        这个表显示了浏览器左侧的数据。
        设置“navigation_table_class”属性
        所需的:类:horizon.tables.DataTable的类。
        这个表类必须在Meta中设置browser_table属性navigation。

    .. attribute:: content_table_class

        This table displays data on the right side of the browser.
        Set the ``content_table_class`` attribute with
        the desired :class:`~horizon.tables.DataTable` class.
        This table class must set browser_table attribute in Meta to
        ``"content"``.
        此表显示浏览器右侧的数据。
        设置“content_table_class”属性
        所需的:类:horizon.tables。DataTable的类。
        这个表类必须在Meta中设置browser_table属性

    .. attribute:: navigation_kwarg_name

        This attribute represents the key of the navigatable items in the
        kwargs property of this browser's view.
        Defaults to ``"navigation_kwarg"``.
        此属性表示导航项的关键这个浏览器视图的kwargs属性。


    .. attribute:: content_kwarg_name

        This attribute represents the key of the content items in the
        kwargs property of this browser's view.
        这个属性代表了内容项的键这个浏览器视图的kwargs属性。
        Defaults to ``"content_kwarg"``.

    .. attribute:: template

        String containing the template which should be used to render the browser.
         Defaults to ``"horizon/common/_resource_browser.html"``.
        包含应该用来呈现浏览器的模板的字符串。
    .. attribute:: context_var_name

        The name of the context variable which will contain the browser when it is rendered.
        上下文变量的名称，它将在呈现时包含浏览器。
         Defaults to ``"browser"``.

    .. attribute:: has_breadcrumb

        Indicates if the content table of the browser would have breadcrumb.
        指示浏览器的内容表是否有面包屑。
        Defaults to false.

    .. attribute:: breadcrumb_template

        This is a template used to render the breadcrumb.
        这是用来渲染面包屑的模板。
        Defaults to ``"horizon/common/_breadcrumb.html"``.
    """
    name = None
    verbose_name = None
    navigation_table_class = None
    content_table_class = None
    navigation_kwarg_name = "navigation_kwarg"
    content_kwarg_name = "content_kwarg"
    navigable_item_name = _("Navigation Item")
    template = "horizon/common/_resource_browser.html"
    context_var_name = "browser"
    has_breadcrumb = False
    breadcrumb_template = "horizon/common/_breadcrumb.html"
    breadcrumb_url = None

    def __init__(self, request, tables_dict=None, attrs=None, **kwargs):
        super(ResourceBrowser, self).__init__()
        self.name = self.name or self.__class__.__name__
        self.verbose_name = self.verbose_name or self.name.title()
        self.request = request
        self.kwargs = kwargs
        self.has_breadcrumb = getattr(self, "has_breadcrumb")
        if self.has_breadcrumb:
            self.breadcrumb_template = getattr(self, "breadcrumb_template")
            self.breadcrumb_url = getattr(self, "breadcrumb_url")
            if not self.breadcrumb_url:
                raise ValueError("You must specify a breadcrumb_url "
                                 "if the has_breadcrumb is set to True.")
        self.attrs.update(attrs or {})
        self.check_table_class(self.content_table_class, "content_table_class")
        self.check_table_class(self.navigation_table_class,
                               "navigation_table_class")
        if tables_dict:
            self.set_tables(tables_dict)

    def check_table_class(self, cls, attr_name):
        if not cls or not issubclass(cls, DataTable):
            raise ValueError("You must specify a DataTable subclass for "
                             "the %s attribute on %s."
                             % (attr_name, self.__class__.__name__))

    def set_tables(self, tables):
        """Sets the table instances on the browser from a dictionary mapping
        table names to table instances (as constructed by MultiTableView).
        将浏览器上的表实例从字典映射表名到表实例(由多tableview构造)。
        """
        self.navigation_table = tables[self.navigation_table_class._meta.name]
        self.content_table = tables[self.content_table_class._meta.name]
        navigation_item = self.kwargs.get(self.navigation_kwarg_name)
        content_path = self.kwargs.get(self.content_kwarg_name)
        if self.has_breadcrumb:
            self.prepare_breadcrumb(tables, navigation_item, content_path)

    def prepare_breadcrumb(self, tables, navigation_item, content_path):
        if self.has_breadcrumb and navigation_item and content_path:
            for table in tables.values():
                table.breadcrumb = Breadcrumb(self.request,
                                              self.breadcrumb_template,
                                              navigation_item,
                                              content_path,
                                              self.breadcrumb_url)

    def render(self):
        browser_template = template.loader.get_template(self.template)
        extra_context = {self.context_var_name: self}
        context = template.RequestContext(self.request, extra_context)
        return browser_template.render(context)
