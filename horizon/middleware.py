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
Middleware provided and used by Horizon.
提供和使用的中间件。
"""

import json
import logging
import time

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME  # noqa
from django.contrib.auth.views import redirect_to_login  # noqa
from django.contrib import messages as django_messages
from django import http
from django import shortcuts
from django.utils.encoding import iri_to_uri  # noqa
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from openstack_auth import utils as auth_utils
from openstack_auth import views as auth_views
import six

from horizon import exceptions
from horizon.utils import functions as utils


LOG = logging.getLogger(__name__)


class HorizonMiddleware(object):
    """The main Horizon middleware class. Required for use of Horizon.
    主要的Horizon中间件类。要求使用地Horizon。"""

    logout_reason = None

    def _check_has_timed_timeout(self, request):
        """Check for session timeout and return timestamp.
        检查会话超时和返回时间戳。"""
        has_timed_out = False
        # Activate timezone handling激活时区处理
        tz = request.session.get('django_timezone')
        if tz:
            timezone.activate(tz)
        try:
            timeout = settings.SESSION_TIMEOUT
        except AttributeError:
            timeout = 1800
        last_activity = request.session.get('last_activity', None)
        timestamp = int(time.time())
        if (
            hasattr(request, "user")
            and hasattr(request.user, "token")
            and not auth_utils.is_token_valid(request.user.token)
        ):
            # The user was logged in, but his keystone token expired.
            # 用户登录了，但他的keystone标记过期了。
            has_timed_out = True
        if isinstance(last_activity, int):
            if (timestamp - last_activity) > timeout:
                has_timed_out = True
            if has_timed_out:
                request.session.pop('last_activity')
        return (has_timed_out, timestamp)

    def _logout(self, request, login_url=None, message=None):
        """Logout a user and display a logout message.
        注销一个用户并显示一个注销消息。"""
        response = auth_views.logout(request, login_url)
        if message is not None:
            self.logout_reason = message
            utils.add_logout_reason(request, response, message)
        return response

    def process_request(self, request):
        """Adds data necessary for Horizon to function to the request.
        增加需要的数据来满足请求的功能。"""

        request.horizon = {'dashboard': None,
                           'panel': None,
                           'async_messages': []}
        if not hasattr(request, "user") or not request.user.is_authenticated():
            # proceed no further if the current request is already known
            # not to be authenticated
            # it is CRITICAL to perform this check as early as possible
            # to avoid creating too many sessions
            # 如果当前请求已经不被确认，那么就继续进行下去，因为要尽早执行此检查，以避免创建过多的会话
            return None

        # Check for session timeout if user is (or was) authenticated.
        # 如果用户是经过身份验证的，检查会话超时。
        has_timed_out, timestamp = self._check_has_timed_timeout(request)
        if has_timed_out:
            return self._logout(request, request.path, _("Session timed out."))

        if request.is_ajax():
            # if the request is Ajax we do not want to proceed, as clients can
            #  1) create pages with constant polling, which can create race
            #     conditions when a page navigation occurs
            #  2) might leave a user seemingly left logged in forever
            #  3) thrashes db backed session engines with tons of changes
            # 如果请求是Ajax，我们不希望继续进行，因为客户可以
            # 1)创建具有常量轮询的页面，当页面导航发生时，它可以创建竞态条件
            # 2)可能会让一个用户似乎永远登录了
            # 3)通过大量的更改来使用db支持的会话引擎
            return None
        # If we use cookie-based sessions, check that the cookie size does not
        # reach the max size accepted by common web browsers.
        # 如果我们使用基于cookie的会话，请检查cookie大小是否达到普通web浏览器所接受的最大尺寸。
        if (
            settings.SESSION_ENGINE ==
            'django.contrib.sessions.backends.signed_cookies'
        ):
            max_cookie_size = getattr(
                settings, 'SESSION_COOKIE_MAX_SIZE', None)
            session_cookie_name = getattr(
                settings, 'SESSION_COOKIE_NAME', None)
            session_key = request.COOKIES.get(session_cookie_name)
            if max_cookie_size is not None and session_key is not None:
                cookie_size = sum((
                    len(key) + len(value)
                    for key, value in six.iteritems(request.COOKIES)
                ))
                if cookie_size >= max_cookie_size:
                    LOG.error(
                        'Total Cookie size for user_id: %(user_id)s is '
                        '%(cookie_size)sB >= %(max_cookie_size)sB. '
                        'You need to configure file-based or database-backed '
                        'sessions instead of cookie-based sessions: '
                        'http://docs.openstack.org/developer/horizon/topics/'
                        'deployment.html#session-storage'
                        % {
                            'user_id': request.session.get(
                                'user_id', 'Unknown'),
                            'cookie_size': cookie_size,
                            'max_cookie_size': max_cookie_size,
                        }
                    )
        # We have a valid session, so we set the timestamp
        # 我们有一个有效的会话，所以我们设置了时间戳
        request.session['last_activity'] = timestamp

    def process_exception(self, request, exception):
        """Catches internal Horizon exception classes such as NotAuthorized,
        NotFound and Http302 and handles them gracefully.
        捕获内部视界异常类，如没有授权，NotFound和Http302，并优雅地处理它们。
        """
        if isinstance(exception, (exceptions.NotAuthorized,
                                  exceptions.NotAuthenticated)):
            auth_url = settings.LOGIN_URL
            next_url = iri_to_uri(request.get_full_path())
            if next_url != auth_url:
                field_name = REDIRECT_FIELD_NAME
            else:
                field_name = None
            login_url = request.build_absolute_uri(auth_url)
            response = redirect_to_login(next_url, login_url=login_url,
                                         redirect_field_name=field_name)
            if isinstance(exception, exceptions.NotAuthorized):
                logout_reason = _("Unauthorized. Please try logging in again.")
                utils.add_logout_reason(request, response, logout_reason)
                # delete messages, created in get_data() method
                # 删除消息，在get_data()方法中创建
                # since we are going to redirect user to the login page
                # 因为我们要将用户重定向到登录页面
                response.delete_cookie('messages')

            if request.is_ajax():
                response_401 = http.HttpResponse(status=401)
                response_401['X-Horizon-Location'] = response['location']
                return response_401

            return response

        # If an internal "NotFound" error gets this far, return a real 404.
        # 如果一个内部的“NotFound”错误得到了这么多，返回一个真正的404。
        if isinstance(exception, exceptions.NotFound):
            raise http.Http404(exception)

        if isinstance(exception, exceptions.Http302):
            # TODO(gabriel): Find a way to display an appropriate message to
            # the user *on* the login form...
            return shortcuts.redirect(exception.location)

    def process_response(self, request, response):
        """Convert HttpResponseRedirect to HttpResponse if request is via ajax
        to allow ajax request to redirect url
        如果请求通过ajax，则将HttpResponseRedirect转换为HttpResponse
        允许ajax请求重定向url
        """
        if request.is_ajax() and hasattr(request, 'horizon'):
            queued_msgs = request.horizon['async_messages']
            if type(response) == http.HttpResponseRedirect:
                # Drop our messages back into the session as per usual so they
                # don't disappear during the redirect. Not that we explicitly
                # use django's messages methods here.
                # 按惯例将我们的消息返回到会话中，这样它们就不会在重定向期间消失。
                # 并不是我们在这里显式地使用django的消息方法。
                for tag, message, extra_tags in queued_msgs:
                    getattr(django_messages, tag)(request, message, extra_tags)
                if response['location'].startswith(settings.LOGOUT_URL):
                    redirect_response = http.HttpResponse(status=401)
                    # This header is used for handling the logout in JS
                    # 这个头用于处理JS中的注销
                    redirect_response['logout'] = True
                    if self.logout_reason is not None:
                        utils.add_logout_reason(
                            request, redirect_response, self.logout_reason)
                else:
                    redirect_response = http.HttpResponse()
                # Use a set while checking if we want a cookie's attributes
                # 在检查是否需要cookie的属性时使用set
                # copied
                cookie_keys = set(('max_age', 'expires', 'path', 'domain',
                                   'secure', 'httponly', 'logout_reason'))
                # Copy cookies from HttpResponseRedirect towards HttpResponse
                # 从HttpResponseRedirect复制cookie到HttpResponse
                for cookie_name, cookie in six.iteritems(response.cookies):
                    cookie_kwargs = dict((
                        (key, value) for key, value in six.iteritems(cookie)
                        if key in cookie_keys and value
                    ))
                    redirect_response.set_cookie(
                        cookie_name, cookie.value, **cookie_kwargs)
                redirect_response['X-Horizon-Location'] = response['location']
                return redirect_response
            if queued_msgs:
                # TODO(gabriel): When we have an async connection to the
                # client (e.g. websockets) this should be pushed to the
                # socket queue rather than being sent via a header.
                # The header method has notable drawbacks (length limits,
                # etc.) and is not meant as a long-term solution.
                # 客户端 (例如websockets)
                # 应该将其推到套接字队列，而不是通过消息头发送。
                # 标题方法有明显的缺点 (长度限制等)，并不是一个长期的解决方案。
                response['X-Horizon-Messages'] = json.dumps(queued_msgs)
        return response