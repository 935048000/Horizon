# coding=utf-8
# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
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
URL patterns for the OpenStack Dashboard.
OpenStack仪表板的URL模式。
"""

from django.conf import settings
from django.conf.urls import include
from django.conf.urls import patterns
from django.conf.urls.static import static  # noqa
from django.conf.urls import url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns  # noqa

import horizon

urlpatterns = patterns(
    '',
    # 匹配网站根目录的URL，映射到openstack_dashboard.views.splash视图。
    url(r'^$', 'openstack_dashboard.views.splash', name='splash'),
    # 任何以/api/开头的URL将会匹配,引入openstack_dashboard.api.rest.urls
    url(r'^api/', include('openstack_dashboard.api.rest.urls')),
    # 任何访问URL将会匹配,都引用horizon.urls
    url(r'', include(horizon.urls)),
    #horizon.urls对应的是horizon.baise._lazy_urls(),执行之前导入horizon包加载_lazy_urls()方法中的
    #def url_patterns():
    #   return self._urls()[0]
)

for u in getattr(settings, 'AUTHENTICATION_URLS', ['openstack_auth.urls']):
    urlpatterns += patterns(
        '',
        url(r'^auth/', include(u))
    )

# Development static app and project media serving using the staticfiles app.
urlpatterns += staticfiles_urlpatterns()

# Convenience function for serving user-uploaded media during
# development. Only active if DEBUG==True and the URL prefix is a local
# path. Production media should NOT be served by Django.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += patterns(
        '',
        url(r'^500/$', 'django.views.defaults.server_error')
    )
