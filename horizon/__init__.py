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

""" The Horizon interface.
Horizon上的接口。

Contains the core Horizon
包含核心Horizon
classes--
:class:`~horizon.Dashboard` and
:class:`horizon.Panel`
--the dynamic URLconf for Horizon, and common interface
动态URLconf的视界和公共接口
methods like :func:`~horizon.register` and :func:`~horizon.unregister`.
方法如
"""
# Because this module is compiled by setup.py before Django may be installed
# in the environment we try importing Django and issue a warning but move on
# should that fail.
#因为这个模块是由安装程序编译的。在Django之前可以安装py
#在环境中，我们尝试导入Django并发出警告，但继续前进

Horizon = None
try:
    from horizon.base import Dashboard  # noqa
    from horizon.base import Horizon  # noqa
    from horizon.base import Panel  # noqa
    from horizon.base import PanelGroup  # noqa
except ImportError:
    import warnings

    def simple_warn(message, category, filename, lineno, file=None, line=None):
        return '%s: %s' % (category.__name__, message)

    msg = ("Could not import Horizon dependencies. "
           "This is normal during installation.\n")
    warnings.formatwarning = simple_warn
    warnings.warn(msg, Warning)

if Horizon:
    register = Horizon.register
    unregister = Horizon.unregister
    get_absolute_url = Horizon.get_absolute_url
    get_user_home = Horizon.get_user_home
    get_dashboard = Horizon.get_dashboard
    get_default_dashboard = Horizon.get_default_dashboard
    get_dashboards = Horizon.get_dashboards
    urls = Horizon._lazy_urls

# silence flake8 about unused imports here:
# 关于未使用进口的沉默，这里:
__all__ = [
    "Dashboard",
    "Horizon",
    "Panel",
    "PanelGroup",
    "register",
    "unregister",
    "get_absolute_url",
    "get_user_home",
    "get_dashboard",
    "get_default_dashboard",
    "get_dashboards",
    "urls",
]
