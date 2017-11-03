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
Context processors used by Horizon.
用于Horizon的上下文处理器。
"""

from horizon import conf


def horizon(request):
    """The main Horizon context processor. Required for Horizon to function.
    主水平上下文处理器。需要Horizon的功能。

    It adds the Horizon config to the context as well as setting the names
    ``True`` and ``False`` in the context to their boolean equivalents
    for convenience.
    它将Horizon配置添加到上下文，并将名称的“True”和“False”设置为在其布尔值中以方便。

    .. warning::

        Don't put API calls in context processors; they will be called once
        for each template/template fragment which takes context that is used
        to render the complete output.
        不要在上下文处理器中调用API调用;它们将被调用一次，用于每个模板/模板片段，
        它们使用用于呈现完整输出的上下文。
    """
    context = {"HORIZON_CONFIG": conf.HORIZON_CONFIG,
               "True": True,
               "False": False}

    return context
