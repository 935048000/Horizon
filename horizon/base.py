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

"""
Contains the core classes and functionality that makes Horizon what it is.
This module is considered internal, and should not be relied on directly.

Public APIs are made available through the :mod:`horizon` module and
the classes contained therein.
包含核心类和功能，使Horizon成为现实。
这个模块是内部的，不应该直接依赖。
公共api通过:“Horizon”模块和
其中所包含的类。

base.py实现了一套dashboard/panel注册、动态加载机制,
使得Horizon面板上所有的dashboard都是”可插拔”的,
所有的panel都是”动态加载”的
"""

import collections
import copy
import inspect
import logging
import os

from django.conf import settings
from django.conf.urls import include
from django.conf.urls import patterns
from django.conf.urls import url
from django.core.exceptions import ImproperlyConfigured  # noqa
from django.core.urlresolvers import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import SimpleLazyObject  # noqa
from django.utils.importlib import import_module  # noqa
from django.utils.module_loading import module_has_submodule  # noqa
from django.utils.translation import ugettext_lazy as _
import six

from horizon import conf
from horizon.decorators import _current_component  # noqa
from horizon.decorators import require_auth  # noqa
from horizon.decorators import require_perms  # noqa
from horizon import loaders


LOG = logging.getLogger(__name__)


def _decorate_urlconf(urlpatterns, decorator, *args, **kwargs):
    for pattern in urlpatterns:
        if getattr(pattern, 'callback', None):
            pattern._callback = decorator(pattern.callback, *args, **kwargs)
        if getattr(pattern, 'url_patterns', []):
            _decorate_urlconf(pattern.url_patterns, decorator, *args, **kwargs)


# FIXME(lhcheng): We need to find a better way to cache the result.
# Rather than storing it in the session, we could leverage the Django
# session. Currently, this has been causing issue with cookie backend,
# adding 1600+ in the cookie size.
def access_cached(func):
    def inner(self, context):
        session = context['request'].session
        try:
            if session['allowed']['valid_for'] != session.get('token'):
                raise KeyError()
        except KeyError:
            session['allowed'] = {"valid_for": session.get('token')}

        key = "%s.%s" % (self.__class__.__module__, self.__class__.__name__)
        if key not in session['allowed']:
            session['allowed'][key] = func(self, context)
            session.modified = True
        return session['allowed'][key]
    return inner


class NotRegistered(Exception):
    pass


@python_2_unicode_compatible
class HorizonComponent(object):
    policy_rules = None

    def __init__(self):
        super(HorizonComponent, self).__init__()
        if not self.slug:
            raise ImproperlyConfigured('Every %s must have a slug.'
                                       % self.__class__)

    def __str__(self):
        name = getattr(self, 'name', u"Unnamed %s" % self.__class__.__name__)
        return name

    def _get_default_urlpatterns(self):
        package_string = '.'.join(self.__module__.split('.')[:-1])
        if getattr(self, 'urls', None):
            try:
                mod = import_module('.%s' % self.urls, package_string)
            except ImportError:
                mod = import_module(self.urls)
            urlpatterns = mod.urlpatterns
        else:
            # Try importing a urls.py from the dashboard package
            # 尝试导入一个url。来自仪表板包的py
            if module_has_submodule(import_module(package_string), 'urls'):
                urls_mod = import_module('.urls', package_string)
                urlpatterns = urls_mod.urlpatterns
            else:
                urlpatterns = patterns('')
        return urlpatterns

    # FIXME(lhcheng): Removed the access_cached decorator for now until
    # a better implementation has been figured out. This has been causing
    # issue with cookie backend, adding 1600+ in the cookie size.
    # @access_cached
    def can_access(self, context):
        """Return whether the user has role based access to this component.
        返回用户是否对该组件有基于角色的访问。
        This method is not intended to be overridden.
        The result of the method is stored in per-session cache.
        """
        return self.allowed(context)

    def allowed(self, context):
        """Checks if the user is allowed to access this component.
        检查用户是否被允许访问该组件。
        This method should be overridden to return the result of
        any policy checks required for the user to access this component
        when more complex checks are required.
        """
        return self._can_access(context['request'])

    def _can_access(self, request):
        policy_check = getattr(settings, "POLICY_CHECK_FUNCTION", None)

        # this check is an OR check rather than an AND check that is the
        # default in the policy engine, so calling each rule individually
        # 检查是默认在策略引擎中，因此分别调用每个规则
        if policy_check and self.policy_rules:
            for rule in self.policy_rules:
                if policy_check((rule,), request):
                    return True
            return False

        # default to allowed
        # 默认允许
        return True


class Registry(object):
    def __init__(self):
        self._registry = {}
        if not getattr(self, '_registerable_class', None):
            raise ImproperlyConfigured('Subclasses of Registry must set a '
                                       '"_registerable_class" property.')

    def _register(self, cls):
        """Registers the given class.
            注册类。

        If the specified class is already registered then it is ignored.
        如果指定的类已经注册，那么它将被忽略。
        """
        if not inspect.isclass(cls):
            raise ValueError('Only classes may be registered.')
        elif not issubclass(cls, self._registerable_class):
            raise ValueError('Only %s classes or subclasses may be registered.'
                             % self._registerable_class.__name__)

        if cls not in self._registry:
            cls._registered_with = self
            self._registry[cls] = cls()

        return self._registry[cls]

    def _unregister(self, cls):
        """Unregisters the given class.
            注销给定的类。
        If the specified class isn't registered, ``NotRegistered`` will
        be raised.
        如果指定的课程没有注册，“将会”提高
        """
        if not issubclass(cls, self._registerable_class):
            raise ValueError('Only %s classes or subclasses may be '
                             'unregistered.' % self._registerable_class)

        if cls not in self._registry.keys():
            raise NotRegistered('%s is not registered' % cls)

        del self._registry[cls]

        return True

    def _registered(self, cls):
        if inspect.isclass(cls) and issubclass(cls, self._registerable_class):
            found = self._registry.get(cls, None)
            if found:
                return found
        else:
            # Allow for fetching by slugs as well.
            for registered in self._registry.values():
                if registered.slug == cls:
                    return registered
        class_name = self._registerable_class.__name__
        if hasattr(self, "_registered_with"):
            parent = self._registered_with._registerable_class.__name__
            raise NotRegistered('%(type)s with slug "%(slug)s" is not '
                                'registered with %(parent)s "%(name)s".'
                                % {"type": class_name,
                                   "slug": cls,
                                   "parent": parent,
                                   "name": self.slug})
        else:
            slug = getattr(cls, "slug", cls)
            raise NotRegistered('%(type)s with slug "%(slug)s" is not '
                                'registered.' % {"type": class_name,
                                                 "slug": slug})


class Panel(HorizonComponent):
    """A base class for defining Horizon dashboard panels.
        用于定义水平仪表板面板的基类。
    All Horizon dashboard panels should extend from this class. It provides
    the appropriate hooks for automatically constructing URLconfs, and
    providing permission-based access control.
    所有的地平线仪表板面板都应该从这个类扩展。它提供了
    用于自动构造URLconfs的适当钩子
    提供基于许可的访问控制。

    .. attribute:: name

        The name of the panel. This will be displayed in the
        auto-generated navigation and various other places.
        Default: ``''``.
        面板的名称。这将显示在
        自动生成导航和其他地方。
        默认值:“”“”。

    .. attribute:: slug

        A unique "short name" for the panel. The slug is used as
        a component of the URL path for the panel. Default: ``''``.
        一个独特的“短名称”用于面板。蛞蝓被用作
        面板的URL路径的组件。默认值:“”“”。

    .. attribute:: permissions

        A list of permission names, all of which a user must possess in order
        to access any view associated with this panel. This attribute
        is combined cumulatively with any permissions required on the
        ``Dashboard`` class with which it is registered.
        一个用户必须拥有的权限名称列表
        访问与该面板相关的任何视图。这个属性
        是否与所需要的任何权限相结合
        “仪表板”的类，它是注册的。

    .. attribute:: urls

        Path to a URLconf of views for this panel using dotted Python
        notation. If no value is specified, a file called ``urls.py``
        living in the same package as the ``panel.py`` file is used.
        Default: ``None``.
        使用虚线Python对这个面板的视图的URLconf的路径
        符号。如果没有指定值，则会有一个名为“urls.py”的文件。
        和“小组”住在同一个包里。使用py”文件。
        默认值:' '没有' '。

    .. attribute:: nav
    .. method:: nav(context)

        The ``nav`` attribute can be either boolean value or a callable
        which accepts a ``RequestContext`` object as a single argument
        to control whether or not this panel should appear in
        automatically-generated navigation. Default: ``True``.
        “nav”属性可以是布尔值，也可以是可调用的
        哪个接受一个“请求上下文”的对象作为一个参数
        控制面板是否应该出现
        自动生成导航。默认值:' 'True' '。

    .. attribute:: index_url_name

        The ``name`` argument for the URL pattern which corresponds to
        the index view for this ``Panel``. This is the view that
        :meth:`.Panel.get_absolute_url` will attempt to reverse.
        这个' ' name ' '参数对应的URL模式
        这个“面板”的索引视图。这是一个观点
        :甲:“.Panel。“get_绝对te_url”将尝试反转。

    .. staticmethod:: can_register

        This optional static method can be used to specify conditions that
        need to be satisfied to load this panel. Unlike ``permissions`` and
        ``allowed`` this method is intended to handle settings based
        conditions rather than user based permission and policy checks.
        The return value is boolean. If the method returns ``True``, then the
        panel will be registered and available to user (if ``permissions`` and
        ``allowed`` runtime checks are also satisfied). If the method returns
        ``False``, then the panel will not be registered and will not be
        available via normal navigation or direct URL access.
        这个可选的静态方法可用于指定条件
        加载这个面板需要满足。与' '和' '权限
        ‘允许’这个方法是用来处理基于设置的
        条件，而不是基于用户的权限和策略检查。
        返回值是布尔值。如果方法返回' True '，那么
        面板将被注册，并可用于用户(如果“权限”和)
        “‘允许’‘运行时检查’也得到了满足。”如果方法返回
        “‘False’”，那么这个面板将不会被注册，也不会被注册
    """
    name = ''
    slug = ''
    urls = None
    nav = True
    index_url_name = "index"

    def __repr__(self):
        return "<Panel: %s>" % self.slug

    def get_absolute_url(self):
        """Returns the default URL for this panel.
            返回该面板的默认URL。

        The default URL is defined as the URL pattern with ``name="index"`` in
        the URLconf for this panel.

        """
        try:
            return reverse('horizon:%s:%s:%s' % (self._registered_with.slug,
                                                 self.slug,
                                                 self.index_url_name))
        except Exception as exc:
            # Logging here since this will often be called in a template
            # where the exception would be hidden.
            #   这里的日志记录通常是在模板中调用的
            #   异常将隐藏在何处。
            LOG.info("Error reversing absolute URL for %s: %s" % (self, exc))
            raise

    @property
    def _decorated_urls(self):
        urlpatterns = self._get_default_urlpatterns()

        # Apply access controls to all views in the patterns
        # 对模式中的所有视图应用访问控制
        permissions = getattr(self, 'permissions', [])
        _decorate_urlconf(urlpatterns, require_perms, permissions)
        _decorate_urlconf(urlpatterns, _current_component, panel=self)

        # Return the three arguments to django.conf.urls.include
        # 将三个参数返回给django.conf.urls.include。
        return urlpatterns, self.slug, self.slug


@six.python_2_unicode_compatible
class PanelGroup(object):
    """A container for a set of :class:`~horizon.Panel` classes.
        装着一组的horizon.Panel类的容器

    When iterated, it will yield each of the ``Panel`` instances it contains.
    迭代时，它将产生每个“面板”实例。

    .. attribute:: slug

        A unique string to identify this panel group. Required.
        一个唯一的字符串来标识这个面板组。必需的。

    .. attribute:: name

        A user-friendly name which will be used as the group heading in
        places such as the navigation. Default: ``None``.
        一种用户友好的名字，将被用作该群组的标题 比如导航。

    .. attribute:: panels

        A list of panel module names which should be contained within this grouping.
        应该包含在这个分组中的面板模块名称的列表。
    """
    def __init__(self, dashboard, slug=None, name=None, panels=None):
        self.dashboard = dashboard
        self.slug = slug or getattr(self, "slug", "default")
        self.name = name or getattr(self, "name", None)
        # Our panels must be mutable so it can be extended by others.
        self.panels = list(panels or getattr(self, "panels", []))

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.slug)

    def __str__(self):
        return self.name

    def __iter__(self):
        panel_instances = []
        for name in self.panels:
            try:
                panel_instances.append(self.dashboard.get_panel(name))
            except NotRegistered as e:
                LOG.debug(e)
        return iter(panel_instances)


class Dashboard(Registry, HorizonComponent):
    """A base class for defining Horizon dashboards.
    用于定义水平指示板的基类。

    All Horizon dashboards should extend from this base class. It provides the
    appropriate hooks for automatic discovery of :class:`~horizon.Panel`
    modules, automatically constructing URLconfs, and providing
    permission-based access control.
    所有的地平线指示板都应该从这个基类扩展。它提供了
    适当的挂钩，自动发现:“~水平。面板”
    模块，自动构建URLconfs，提供
    采用访问控制。

    .. attribute:: name

        The name of the dashboard. This will be displayed in the
        auto-generated navigation and various other places.
        Default: ``''``.
        仪表板的名称。这将显示在自动生成导航和其他地方。

    .. attribute:: slug

        A unique "short name" for the dashboard. The slug is used as
        a component of the URL path for the dashboard. Default: ``''``.
        仪表板的唯一“short name”。蛞蝓被用作仪表板的URL路径的组件。

    .. attribute:: panels

        The ``panels`` attribute can be either a flat list containing the name
        of each panel **module**  which should be loaded as part of this
        dashboard, or a list of :class:`~horizon.PanelGroup` classes which
        define groups of panels as in the following example::
        “panels”属性可以是包含名称的平面列表
        每个面板* *模块* *，应该作为其中的一部分载入
        仪表盘，或列表:horizon.PanelGroup的类
        定义小组的小组，如以下例子::

            class SystemPanels(horizon.PanelGroup):
                slug = "syspanel"
                name = _("System")
                panels = ('overview', 'instances', ...)

            class Syspanel(horizon.Dashboard):
                panels = (SystemPanels,)

        Automatically generated navigation will use the order of the
        modules in this attribute.
        自动生成的导航将使用模块在这个属性。

        Default: ``[]``.

        .. warning::

            The values for this attribute should not correspond to the
            :attr:`~.Panel.name` attributes of the ``Panel`` classes.
            They should be the names of the Python modules in which the
            ``panel.py`` files live. This is used for the automatic
            loading and registration of ``Panel`` classes much like
            Django's ``ModelAdmin`` machinery.
            此属性的值不应对应于attr:`~.Panel.name`的属性``Panel``类
            它们应该是Python模块的名称``panel.py``活的文件。这是用于自动的
            加载和登记``Panel``类就像Django的``ModelAdmin``

            Panel modules must be listed in ``panels`` in order to be
            discovered by the automatic registration mechanism.
            面板模块必须在“panels”中列出由自动注册机构发现。

    .. attribute:: default_panel

        The name of the panel which should be treated as the default
        panel for the dashboard, i.e. when you visit the root URL
        for this dashboard, that's the panel that is displayed.
        Default: ``None``.
        应该作为默认值处理的面板的名称
        仪表板的面板，即当您访问根URL时
        对于这个仪表板，这是显示的面板。

    .. attribute:: permissions

        A list of permission names, all of which a user must possess in order
        to access any panel registered with this dashboard. This attribute
        is combined cumulatively with any permissions required on individual
        :class:`~horizon.Panel` classes.
        一个用户必须拥有的权限名称列表
        使用该仪表板注册的任何面板。这个属性
        是否与个人需要的权限相结合
        :类:“~horizon.Panel”类。

    .. attribute:: urls

        Optional path to a URLconf of additional views for this dashboard
        which are not connected to specific panels. Default: ``None``.
        可选的路径到URLconf的附加视图的仪表板没有连接到特定的面板。

    .. attribute:: nav
    .. method:: nav(context)

        The ``nav`` attribute can be either boolean value or a callable
        which accepts a ``RequestContext`` object as a single argument
        to control whether or not this dashboard should appear in
        automatically-generated navigation. Default: ``True``.
        “nav”属性可以是布尔值，也可以是可调用的
        哪个接受一个“RequestContext”的对象作为一个参数
        为了控制这个仪表板是否应该出现
        自动生成导航。

    .. attribute:: public

        Boolean value to determine whether this dashboard can be viewed
        without being logged in. Defaults to ``False``.
        布尔值以确定是否可以查看此仪表板没有登录。

    """
    _registerable_class = Panel
    name = ''
    slug = ''
    urls = None
    panels = []
    default_panel = None
    nav = True
    public = False

    def __repr__(self):
        return "<Dashboard: %s>" % self.slug

    def __init__(self, *args, **kwargs):
        super(Dashboard, self).__init__(*args, **kwargs)
        self._panel_groups = None

    def get_panel(self, panel):
        """Returns the specified :class:`~horizon.Panel` instance registered
        with this dashboard.
        返回指定:类:horizon.Panel的实例注册这个指示板。
        """
        return self._registered(panel)

    def get_panels(self):
        """Returns the :class:`~horizon.Panel` instances registered with this
        dashboard in order, without any panel groupings.
        返回:类:horizon.Panel。在此注册的面板实例指示板，没有任何面板分组。
        """
        all_panels = []
        panel_groups = self.get_panel_groups()
        for panel_group in panel_groups.values():
            all_panels.extend(panel_group)
        return all_panels

    def get_panel_group(self, slug):
        """Returns the specified :class:~horizon.PanelGroup
        or None if not registered
        返回指定的类:~ horizon.PanelGroup或者没有注册
        """
        return self._panel_groups.get(slug)

    def get_panel_groups(self):
        registered = copy.copy(self._registry)
        panel_groups = []

        # Gather our known panels
        # 收集我们已知的面板
        if self._panel_groups is not None:
            for panel_group in self._panel_groups.values():
                for panel in panel_group:
                    registered.pop(panel.__class__)
                panel_groups.append((panel_group.slug, panel_group))

        # Deal with leftovers (such as add-on registrations)
        # 处理剩余物(如附加注册)
        if len(registered):
            slugs = [panel.slug for panel in registered.values()]
            new_group = PanelGroup(self,
                                   slug="other",
                                   name=_("Other"),
                                   panels=slugs)
            panel_groups.append((new_group.slug, new_group))
        return collections.OrderedDict(panel_groups)

    def get_absolute_url(self):
        """Returns the default URL for this dashboard.
            返回该仪表板的默认URL。

        The default URL is defined as the URL pattern with ``name="index"``
        in the URLconf for the :class:`~horizon.Panel` specified by
        :attr:`~horizon.Dashboard.default_panel`.
        """
        try:
            return self._registered(self.default_panel).get_absolute_url()
        except Exception:
            # Logging here since this will often be called in a template
            # 这里的日志记录通常是在模板中调用的
            # where the exception would be hidden.
            LOG.exception("Error reversing absolute URL for %s." % self)
            raise

    @property
    def _decorated_urls(self):
        urlpatterns = self._get_default_urlpatterns()

        default_panel = None

        # Add in each panel's views except for the default view.
        # 除了默认视图之外，添加每个面板的视图。
        for panel in self._registry.values():
            if panel.slug == self.default_panel:
                default_panel = panel
                continue
            url_slug = panel.slug.replace('.', '/')
            urlpatterns += patterns('',
                                    url(r'^%s/' % url_slug,
                                        include(panel._decorated_urls)))
        # Now the default view, which should come last
        # 现在默认的视图应该是最后的
        if not default_panel:
            raise NotRegistered('The default panel "%s" is not registered.'
                                % self.default_panel)
        urlpatterns += patterns('',
                                url(r'',
                                    include(default_panel._decorated_urls)))

        # Require login if not public.
        # 如果不公开，则需要登入。
        if not self.public:
            _decorate_urlconf(urlpatterns, require_auth)
        # Apply access controls to all views in the patterns
        # 对模式中的所有视图应用访问控制
        permissions = getattr(self, 'permissions', [])
        _decorate_urlconf(urlpatterns, require_perms, permissions)
        _decorate_urlconf(urlpatterns, _current_component, dashboard=self)

        # Return the three arguments to django.conf.urls.include
        # 将三个参数返回给django.conf.url。
        return urlpatterns, self.slug, self.slug

    def _autodiscover(self):
        """Discovers panels to register from the current dashboard module.
        从当前仪表板模块中发现面板进行注册。

        从“settings.INSTALLED_APPS发现模块，
        包含dashboard.py文件的模块进行注册，并添加到self._registry注册表中，
        然后通过循环遍历注册表，调用每个注册dashboard的_autodiscover()方法，
        注册每个dashboard下面的panel,完成整个horizon模块的注册，
        最终返回一个urlpatterns值，urls匹配调用相应的views模块。
        """
        if getattr(self, "_autodiscover_complete", False):
            return

        panels_to_discover = []
        panel_groups = []
        # If we have a flat iterable of panel names, wrap it again so
        # we have a consistent structure for the next step.
        # 如果我们有一个平面迭代的面板名称，那么再次包装它
        # 我们在下一步中有一个一致的结构。
        # isinstance: 判断一个对象是否是一个已知的类型
        if all([isinstance(i, six.string_types) for i in self.panels]):
            self.panels = [self.panels]

        # Now iterate our panel sets.
        # 现在遍历我们的panel集。
        for panel_set in self.panels:
            # Instantiate PanelGroup classes.
            # 实例化PanelGroup类。
            if not isinstance(panel_set, collections.Iterable) and \
                    issubclass(panel_set, PanelGroup):
                panel_group = panel_set(self)
            # Check for nested tuples, and convert them to PanelGroups
            # 检查嵌套的元组，并将它们转换为PanelGroups
            elif not isinstance(panel_set, PanelGroup):
                panel_group = PanelGroup(self, panels=panel_set)

            # Put our results into their appropriate places
            # 存放返回结果
            panels_to_discover.extend(panel_group.panels)
            panel_groups.append((panel_group.slug, panel_group))

        self._panel_groups = collections.OrderedDict(panel_groups)

        # Do the actual discovery 做实际的发现
        # 加载panel_groups中的每一个panel
        package = '.'.join(self.__module__.split('.')[:-1])
        mod = import_module(package)
        for panel in panels_to_discover:
            try:
                before_import_registry = copy.copy(self._registry)
                import_module('.%s.panel' % panel, package)
            except Exception:
                self._registry = before_import_registry
                if module_has_submodule(mod, panel):
                    raise
        # 标记自动注册Panel已经完成
        self._autodiscover_complete = True

    @classmethod
    def register(cls, panel):
        """注册一个 :class:`~horizon.Panel` 这个指示板."""
        panel_class = Horizon.register_panel(cls, panel)
        # Support template loading from panel template directories.
        # 支持模板加载模板目录。
        panel_mod = import_module(panel.__module__)
        panel_dir = os.path.dirname(panel_mod.__file__)
        template_dir = os.path.join(panel_dir, "templates")
        if os.path.exists(template_dir):
            key = os.path.join(cls.slug, panel.slug)
            loaders.panel_template_dirs[key] = template_dir
        return panel_class

    @classmethod
    def unregister(cls, panel):
        """注销 :class:`~horizon.Panel` 从这个指示板."""
        success = Horizon.unregister_panel(cls, panel)
        if success:
            # Remove the panel's template directory.
            # 删除面板的模板目录。
            key = os.path.join(cls.slug, panel.slug)
            if key in loaders.panel_template_dirs:
                del loaders.panel_template_dirs[key]
        return success

    def allowed(self, context):
        """Checks for role based access for this dashboard.

        Checks for access to any panels in the dashboard and of the the
        dashboard itself.

        This method should be overridden to return the result of
        any policy checks required for the user to access this dashboard
        when more complex checks are required.
        检查这个仪表板的基于角色的访问。
        检查仪表板和其中的任何面板的访问权限
        仪表板本身。
        应该重写此方法以返回结果
        用户访问此仪表板所需的任何策略检查
        当需要更复杂的检查时。
        """

        # if the dashboard has policy rules, honor those above individual
        # 如果仪表板有政策规则，请尊重上述个人
        # panels
        if not self._can_access(context['request']):
            return False

        # check if access is allowed to a single panel,
        # the default for each panel is True
        # 检查是否允许访问一个面板，
        # 每个面板的默认值为True
        for panel in self.get_panels():
            if panel.can_access(context):
                return True

        return False


class Workflow(object):
    pass

try:
    from django.utils.functional import empty  # noqa
except ImportError:
    # Django 1.3 fallback
    empty = None


class LazyURLPattern(SimpleLazyObject):
    def __iter__(self):
        if self._wrapped is empty:
            self._setup()
        return iter(self._wrapped)

    def __reversed__(self):
        if self._wrapped is empty:
            self._setup()
        return reversed(self._wrapped)

    def __len__(self):
        if self._wrapped is empty:
            self._setup()
        return len(self._wrapped)

    def __getitem__(self, idx):
        if self._wrapped is empty:
            self._setup()
        return self._wrapped[idx]


class Site(Registry, HorizonComponent):
    """The overarching class which encompasses all dashboards and panels.
    包含所有指示板和面板的总体类。"""

    # Required for registry 需要注册
    _registerable_class = Dashboard

    name = "Horizon"
    namespace = 'horizon'
    slug = 'horizon'
    urls = 'horizon.site_urls'

    def __repr__(self):
        return u"<Site: %s>" % self.slug

    @property
    def _conf(self):
        return conf.HORIZON_CONFIG

    @property
    def dashboards(self):
        return self._conf['dashboards']

    @property
    def default_dashboard(self):
        return self._conf['default_dashboard']

    def register(self, dashboard):
        """注册一个 :class:`~horizon.Dashboard` with Horizon."""
        return self._register(dashboard)

    def unregister(self, dashboard):
        """注销 :class:`~horizon.Dashboard` from Horizon."""
        return self._unregister(dashboard)

    def registered(self, dashboard):
        return self._registered(dashboard)

    def register_panel(self, dashboard, panel):
        dash_instance = self.registered(dashboard)
        return dash_instance._register(panel)

    def unregister_panel(self, dashboard, panel):
        dash_instance = self.registered(dashboard)
        if not dash_instance:
            raise NotRegistered("The dashboard %s is not registered."
                                % dashboard)
        return dash_instance._unregister(panel)

    def get_dashboard(self, dashboard):
        """返回指定的 :class:`~horizon.Dashboard` instance."""
        return self._registered(dashboard)

    def get_dashboards(self):
        """返回一个有序的元组:class:`~horizon.Dashboard` 模块.

        按下订单指示板 ``"dashboards"``键入
        ``HORIZON_CONFIG`` 或者返回所有已注册的仪表板
        按字母顺序排列的。

       任何剩余的 :class:`~horizon.Dashboard` classes 注册
        Horizon但没有上市``HORIZON_CONFIG['dashboards']``
        将按字母顺序被追加到列表的末尾。
        """
        if self.dashboards:
            registered = copy.copy(self._registry)
            dashboards = []
            for item in self.dashboards:
                dashboard = self._registered(item)
                dashboards.append(dashboard)
                registered.pop(dashboard.__class__)
            if len(registered):
                extra = sorted(registered.values())
                dashboards.extend(extra)
            return dashboards
        else:
            return sorted(self._registry.values())

    def get_default_dashboard(self):
        """返回默认的 :class:`~horizon.Dashboard` 实例.

        If ``"default_dashboard"`` is specified in ``HORIZON_CONFIG``
        then that dashboard will be returned. If not, the first dashboard
        returned by :func:`~horizon.get_dashboards` will be returned.
        """
        if self.default_dashboard:
            return self._registered(self.default_dashboard)
        elif len(self._registry):
            return self.get_dashboards()[0]
        else:
            raise NotRegistered("No dashboard modules have been registered.")

    def get_user_home(self, user):
        """返回特定用户的默认URL。

        This method can be used to customize where a user is sent when
        they log in, etc. By default it returns the value of
        :meth:`get_absolute_url`.
        此方法可用于自定义在何时发送用户
        他们登录，等等。默认情况下，它返回值

        An alternative function can be supplied to customize this behavior
        by specifying a either a URL or a function which returns a URL via
        the ``"user_home"`` key in ``HORIZON_CONFIG``. Each of these
        would be valid::

            {"user_home": "/home",}  # A URL
            {"user_home": "my_module.get_user_home",}  # Path to a function
            {"user_home": lambda user: "/" + user.name,}  # A function
            {"user_home": None,}  # Will always return the default dashboard

        This can be useful if the default dashboard may not be accessible
        to all users. When user_home is missing from HORIZON_CONFIG,
        it will default to the settings.LOGIN_REDIRECT_URL value.
        """
        user_home = self._conf['user_home']
        if user_home:
            if callable(user_home):
                return user_home(user)
            elif isinstance(user_home, six.string_types):
                # Assume we've got a URL if there's a slash in it
                # 假设我们有一个URL，如果它有一个斜杠
                if '/' in user_home:
                    return user_home
                else:
                    mod, func = user_home.rsplit(".", 1)
                    return getattr(import_module(mod), func)(user)
            # If it's not callable and not a string, it's wrong.
            # 如果它不是可调用的，而不是字符串，那么它是错误的。
            raise ValueError('The user_home setting must be either a string '
                             'or a callable object (e.g. a function).')
        else:
            return self.get_absolute_url()

    def get_absolute_url(self):
        """返回Horizon的URLconf的默认URL。

        The default URL is determined by calling
        :meth:`~horizon.Dashboard.get_absolute_url`
        on the :class:`~horizon.Dashboard` instance returned by
        :meth:`~horizon.get_default_dashboard`.
        """
        return self.get_default_dashboard().get_absolute_url()

    @property
    def _lazy_urls(self):
        """Lazy loading for URL patterns.
            URL模式的延迟加载。
        This method avoids problems associated with attempting to evaluate
        the URLconf before the settings module has been loaded.
        这种方法避免了试图评估的问题设置模块之前的URLconf已经加载。

        完成整个模块注册的入口
         @property 可以将python定义的函数“当做”属性访问。
        """
        def url_patterns():
            #url_patterns作为一个方法引用当作参数。
            return self._urls()[0]
            # LazyURLPattern(url_patterns) 猜测这是一个懒惰方法，load的时候把方法传入，
            # 当需要使用的使用才执行方法。
            # request 请求进来的时候，回去Openstack.urls.py 进行配置，
            # include('openstack_auth.urls')这个时候会执行url_patterns()
            # self.namespace = "horizon"
            # self.slug = "horizon"
        return LazyURLPattern(url_patterns), self.namespace, self.slug

    def _urls(self):
        """Constructs the URLconf for Horizon from registered Dashboards.
        从注册的Dashboards构造出Horizon上的URLconf

        _urls完成所有Dashboard和Panel的注册变编译URLconf"""

        # 获取horizon.site_urls urlpatterns 值
        urlpatterns = self._get_default_urlpatterns()
        # 从“settings.INSTALLED_APPS发现模块，包含dashboard.py、panel.py的模块注册，
        # 添加到注册表中self._registry，没有的抛出异常。
        self._autodiscover()

        # Discover each dashboard's panels.
        # 发现每个dashboard的panels。
        #从注册表self._registry取出注册dashboard，注册每个dashboard中的panel
        for dash in self._registry.values():
            dash._autodiscover()

        # Load the plugin-based panel configuration
        # 加载基于插件的面板配置
        self._load_panel_customization()

        # Allow for override modules
        # 允许重写模块
        if self._conf.get("customization_module", None):
            customization_module = self._conf["customization_module"]
            bits = customization_module.split('.')
            mod_name = bits.pop()
            package = '.'.join(bits)
            mod = import_module(package)
            try:
                before_import_registry = copy.copy(self._registry)
                import_module('%s.%s' % (package, mod_name))
            except Exception:
                self._registry = before_import_registry
                if module_has_submodule(mod, mod_name):
                    raise

        # Compile the dynamic urlconf.
        # 动态urlconf编译。
        for dash in self._registry.values():
            urlpatterns += patterns('',
                                    url(r'^%s/' % dash.slug,
                                        include(dash._decorated_urls)))

        # Return the three arguments to django.conf.urls.include
        # 将三个参数返回给django.conf.urls.include
        return urlpatterns, self.namespace, self.slug

    def _autodiscover(self):
        """Discovers modules to register from ``settings.INSTALLED_APPS``.
        # 发现模块从设置settings.INSTALLED_APPS注册。

        This makes sure that the appropriate modules get imported to register
        themselves with Horizon.
        这确保适当的模块被导入到自己的Horizon寄存器中

        """

        # 判断self对象中是否存在_registerable_class 如果没有抛出异常，
        # 你必须设置一个“registerable_class”属性以使用自动发现。
        # self._registerable_class = <class 'horizon.base.Dashboard'>  这在Class Site中已经设定了。
        if not getattr(self, '_registerable_class', None):
            raise ImproperlyConfigured('You must set a '
                                       '"_registerable_class" property '
                                       'in order to use autodiscovery.')
        # Discover both dashboards and panels, in that order
        # 按此顺序发现仪表板和面板
        for mod_name in ('dashboard', 'panel'):
            for app in settings.INSTALLED_APPS:
                mod = import_module(app)
                try:
                    '''
                        注册表 self._registry ＝ ｛｝
                        定义：class Registry(object):
                                def __init__(self):
                                    self._registry = {}
                                    ......
                        copy.copy():copy.copy 浅拷贝 只拷贝父对象，不会拷贝对象的内部的子对象。
                    '''
                    before_import_registry = copy.copy(self._registry)
                    import_module('%s.%s' % (app, mod_name))
                except Exception:
                    # 如果APP中没有dashboard抛出异常
                    self._registry = before_import_registry
                    if module_has_submodule(mod, mod_name):
                        raise

    def _load_panel_customization(self):
        """Applies the plugin-based panel configurations.
        应用以插件为基础的panel配置。

        This method parses the panel customization from the ``HORIZON_CONFIG``
        and make changes to the dashboard accordingly.

        It supports adding, removing and setting default panels on the
        dashboard. It also support registering a panel group.
        它支持添加、删除和设置默认面板仪表板。它还支持注册一个面板组。
        """
        panel_customization = self._conf.get("panel_customization", [])

        # Process all the panel groups first so that they exist before panels
        # are added to them and Dashboard._autodiscover() doesn't wipe out any
        # panels previously added when its panel groups are instantiated.
        # 首先处理所有的面板组，这样它们就存在于面板之前
        # 被添加到他们和Dashboard._autodiscover()不会清除任何
        # 当面板组被实例化时，前面添加了面板。
        panel_configs = []
        for config in panel_customization:
            if config.get('PANEL'):
                panel_configs.append(config)
            elif config.get('PANEL_GROUP'):
                self._process_panel_group_configuration(config)
            else:
                LOG.warning("Skipping %s because it doesn't have PANEL or "
                            "PANEL_GROUP defined.", config.__name__)
        # 现在处理板。
        for config in panel_configs:
            self._process_panel_configuration(config)

    def _process_panel_configuration(self, config):
        """在仪表板上添加、删除和设置默认面板。"""
        try:
            dashboard = config.get('PANEL_DASHBOARD')
            if not dashboard:
                LOG.warning("Skipping %s because it doesn't have "
                            "PANEL_DASHBOARD defined.", config.__name__)
                return
            panel_slug = config.get('PANEL')
            dashboard_cls = self.get_dashboard(dashboard)
            panel_group = config.get('PANEL_GROUP')
            default_panel = config.get('DEFAULT_PANEL')

            # Set the default panel 设置默认面板
            if default_panel:
                dashboard_cls.default_panel = default_panel

            # Remove the panel 删除面板
            if config.get('REMOVE_PANEL', False):
                for panel in dashboard_cls.get_panels():
                    if panel_slug == panel.slug:
                        dashboard_cls.unregister(panel.__class__)
            elif config.get('ADD_PANEL', None):
                # Add the panel to the dashboard 将面板添加到仪表板
                panel_path = config['ADD_PANEL']
                mod_path, panel_cls = panel_path.rsplit(".", 1)
                try:
                    mod = import_module(mod_path)
                except ImportError:
                    LOG.warning("Could not load panel: %s", mod_path)
                    return
                panel = getattr(mod, panel_cls)
                # test is can_register method is present and call method if
                # it is to determine if the panel should be loaded
                # 测试是can_register方法和调用方法
                # it是确定面板是否应该加载
                if hasattr(panel, 'can_register') and \
                   callable(getattr(panel, 'can_register')):
                    if not panel.can_register():
                        LOG.debug("Load condition failed for panel: %(panel)s",
                                  {'panel': panel_slug})
                        return
                dashboard_cls.register(panel)
                if panel_group:
                    dashboard_cls.get_panel_group(panel_group).\
                        panels.append(panel.slug)
                else:
                    panels = list(dashboard_cls.panels)
                    panels.append(panel)
                    dashboard_cls.panels = tuple(panels)
        except Exception as e:
            LOG.warning('Could not process panel %(panel)s: %(exc)s',
                        {'panel': panel_slug, 'exc': e})

    def _process_panel_group_configuration(self, config):
        """Adds a panel group to the dashboard.向仪表板添加一个面板组。"""
        panel_group_slug = config.get('PANEL_GROUP')
        try:
            dashboard = config.get('PANEL_GROUP_DASHBOARD')
            if not dashboard:
                LOG.warning("Skipping %s because it doesn't have "
                            "PANEL_GROUP_DASHBOARD defined.", config.__name__)
                return
            dashboard_cls = self.get_dashboard(dashboard)

            panel_group_name = config.get('PANEL_GROUP_NAME')
            if not panel_group_name:
                LOG.warning("Skipping %s because it doesn't have "
                            "PANEL_GROUP_NAME defined.", config.__name__)
                return
            # Create the panel group class 创建面板组类
            panel_group = type(panel_group_slug,
                               (PanelGroup, ),
                               {'slug': panel_group_slug,
                                'name': panel_group_name,
                                'panels': []},)
            # Add the panel group to dashboard 将面板组添加到仪表板
            panels = list(dashboard_cls.panels)
            panels.append(panel_group)
            dashboard_cls.panels = tuple(panels)
            # Trigger the autodiscovery to completely load the new panel group
            # 触发自动发现以完全加载新的面板组
            dashboard_cls._autodiscover_complete = False
            dashboard_cls._autodiscover()
        except Exception as e:
            LOG.warning('Could not process panel group %(panel_group)s: '
                        '%(exc)s',
                        {'panel_group': panel_group_slug, 'exc': e})


class HorizonSite(Site):
    """A singleton implementation of Site such that all dealings with horizon
    get the same instance no matter what. There can be only one.
    一个单例实现的网站，如所有与地平线的关系
    无论如何都要得到相同的实例。只有一个。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Site, cls).__new__(cls, *args, **kwargs)
        return cls._instance


# The one true Horizon 实例化
Horizon = HorizonSite()
