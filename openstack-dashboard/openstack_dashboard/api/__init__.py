# coding=utf-8
# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 Nebula, Inc.
# Copyright 2013 Big Switch Networks
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
Methods and interface objects used to interact with external APIs.

API method calls return objects that are in many cases objects with
attributes that are direct maps to the data returned from the API http call.
Unfortunately, these objects are also often constructed dynamically, making
it difficult to know what data is available from the API object.  Because of
this, all API calls should wrap their returned object in one defined here,
using only explicitly defined attributes and/or methods.

In other words, Horizon developers not working on openstack_dashboard.api
shouldn't need to understand the finer details of APIs for
Keystone/Nova/Glance/Swift et. al.

用于与外部api交互的方法和接口对象。
API方法调用在许多情况下对象的返回对象属性是直接映射到从API http调用返回的数据。
不幸的是，这些对象通常也是动态构建很难知道来自API对象的数据是什么。
因为所有API调用都应该将返回的对象包装在这里，只使用显式定义的属性和/或方法。
换句话说，Horizon开发人员不使用openstack_dashboard.api
"""
from openstack_dashboard.api import base
from openstack_dashboard.api import ceilometer
from openstack_dashboard.api import cinder
from openstack_dashboard.api import fwaas
from openstack_dashboard.api import glance
from openstack_dashboard.api import heat
from openstack_dashboard.api import keystone
from openstack_dashboard.api import lbaas
from openstack_dashboard.api import network
from openstack_dashboard.api import neutron
from openstack_dashboard.api import nova
from openstack_dashboard.api import swift
from openstack_dashboard.api import vpn


__all__ = [
    "base",
    "cinder",
    "fwaas",
    "glance",
    "heat",
    "keystone",
    "lbaas",
    "network",
    "neutron",
    "nova",
    "swift",
    "ceilometer",
    "vpn",
]
