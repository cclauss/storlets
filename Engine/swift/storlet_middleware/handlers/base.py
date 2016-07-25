# Copyright (c) 2010-2016 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import urllib
from swift.common.internal_client import InternalClient
from swift.common.swob import HTTPBadRequest, Response, Range
from swift.common.utils import config_true_value

from storlet_gateway.common.exceptions import FileManagementError
from storlet_gateway.common.file_manager import FileManager


class NotStorletRequest(Exception):
    pass


class NotStorletExecution(NotStorletRequest):
    pass


class SwiftFileManager(FileManager):

    def __init__(self, account, storlet_container, dependency_container,
                 log_container, conf_file, logger):
        super(SwiftFileManager, self).__init__()
        self.account = account
        self.storlet_container = storlet_container
        self.dependency_container = dependency_container
        self.log_container = log_container
        self.conf_file = conf_file
        self.logger = logger

    @property
    def client(self):
        # TODO(kota_): IMO, we need to make this to self._client environ to
        #              get rid of redundant instanciation
        return InternalClient(self.conf_file, 'SA', 1)

    def _get_object(self, container, obj, headers=None):
        """
        Utility function to be used to get object from swift

        :param container: container name
        :param obj: object name
        :param headers: request headers
        """
        self.logger.debug('GET object %s/%s/%s from swift' %
                          (self.account, container, obj))
        _, headers, data_iter = \
            self.client.get_object(self.account, container, obj, headers)
        return headers, data_iter

    def _put_object(self, container, obj, headers, fobj):
        """
        Utility function to be used to put object into swift

        :param container: container name
        :param obj: object name
        :param headers: request headers
        :param fobj: file object
        """
        self.logger.debug('PUT object %s/%s/%s to swift' %
                          (self.account, container, obj))
        self.client.upload_object(fobj, self.account, container, headers)

    def get_storlet(self, name):
        self.logger.debug('get storlet file %s from swift' % name)
        try:
            headers, data_iter = \
                self._get_object(self.storlet_container, name)
            return data_iter, None
        except Exception:
            self.logger.exception('Failed to get storlet file '
                                  '%s/%s/%s from swift' %
                                  (self.account, self.storlet_container,
                                   name))
            raise FileManagementError('Failed to get storlet file: %s' % name)

    def get_dependency(self, name):
        self.logger.debug('get dependency file %s from swift' % name)
        try:
            headers, data_iter = \
                self._get_object(self.dependency_container, name)
            perm = headers.get(
                'X-Object-Meta-Storlet-Dependency-Permissions')
            return data_iter, perm
        except Exception:
            self.logger.exception('Failed to get dependency file '
                                  '%s/%s/%s from swift' %
                                  (self.account, self.dependency_container,
                                   name))
            raise FileManagementError('Failed to get dependency file: %s' %
                                      name)

    def put_log(self, name, fobj):
        self.logger.debug('save log file %s into swift' % name)
        try:
            headers = {'CONTENTTYPE': 'text/plain'}
            self._put_object(self.log_container, name, headers, fobj)
        except Exception:
            self.logger.exception('Failed to put log file %s/%s/%s to swift' %
                                  (self.account, self.log_container, name))
            raise FileManagementError('Failed to put log file: %s' % name)


def _request_instance_property():
    """
    Set and retrieve the request instance.
    This works to force to tie the consistency between the request path and
    self.vars (i.e. api_version, account, container, obj) even if unexpectedly
    (separately) assigned.
    """
    def getter(self):
        return self._request

    def setter(self, request):
        self._request = request
        try:
            self._extract_vaco()
        except ValueError:
            raise NotStorletRequest()

    return property(getter, setter,
                    doc="Force to tie the request to acc/con/obj vars")


class StorletBaseHandler(object):
    """
    This is an abstract handler for Proxy/Object Server middleware
    """
    request = _request_instance_property()

    def __init__(self, request, conf, app, logger):
        """
        :param request: swob.Request instance
        :param conf: gatway conf dict
        :param app: wsgi Application
        :param logger: logger instance
        """
        self.reseller_prefix = conf.get('reseller_prefix', 'AUTH')
        self.request = request
        self.app = app
        self.logger = logger
        self.conf = conf
        self.gateway_class = self.conf['gateway_module']
        self.sreq_class = self.gateway_class.request_class
        self.storlet_container = conf.get('storlet_container', 'storlet')
        self.storlet_dependency = conf.get('storlet_dependency', 'dependency')
        self.log_container = conf.get('storlet_logcontainer', 'storletlog')
        self.client_conf_file = '/etc/swift/storlet-proxy-server.conf'

    def _setup_gateway(self):
        """
        Setup gateway instance

        """
        self.gateway = self.gateway_class(
            self.conf, self.logger, self.scope)
        self._update_storlet_parameters_from_headers()

    def _extract_vaco(self):
        """
        Set version, account, container, obj vars from self._parse_vaco result

        :raises ValueError: if self._parse_vaco raises ValueError while
                            parsing, this method doesn't care and raise it to
                            upper caller.
        """
        self._api_version, self._account, self._container, self._obj = \
            self._parse_vaco()

    @property
    def scope(self):
        if self._account.startswith(self.reseller_prefix + '_'):
            start = len(self.reseller_prefix) + 1
        else:
            start = 0
        end = min(start + 13, len(self.account))
        return self._account[start:end]

    @property
    def api_version(self):
        return self._api_version

    @property
    def account(self):
        return self._account

    @property
    def container(self):
        return self._container

    @property
    def obj(self):
        return self._obj

    def _parse_vaco(self):
        """
        Parse method of path from self.request which depends on child class
        (Proxy or Object)

        :return: a string tuple of (version, account, container, object)
        """
        raise NotImplementedError()

    def handle_request(self):
        """
        Run storlet

        """
        raise NotImplementedError()

    @property
    def is_storlet_execution(self):
        """
        Check if the request requires storlet execution

        :return: Whether storlet should be executed
        """
        return 'X-Run-Storlet' in self.request.headers

    @property
    def is_range_request(self):
        """
        Determines whether the request is a byte-range request

        :return: Whether the request is a byte-range request
        """
        return 'Range' in self.request.headers

    @property
    def is_storlet_range_request(self):
        return 'X-Storlet-Range' in self.request.headers

    @property
    def is_storlet_multiple_range_request(self):
        if not self.is_storlet_range_request:
            return False

        r = self.request.headers['X-Storlet-Range']
        return len(Range(r).ranges) > 1

    def _has_run_on_proxy_header(self):
        """
        Check whether there is a header mandating storlet execution on proxy

        :return: Whether a header exists mandating storlet execution on proxy
        """
        if 'X-Storlet-Run-On-Proxy' in self.request.headers:
            if self.request.headers['X-Storlet-Run-On-Proxy'].strip():
                raise HTTPBadRequest('X-Storlet-Run-On-Proxy header should '
                                     'be empty', request=self.request)
            return True
        return False

    @property
    def execute_on_proxy(self):
        return (self._has_run_on_proxy_header() or
                self.conf['storlet_execute_on_proxy_only'])

    @property
    def execute_range_on_proxy(self):
        return (self.is_storlet_multiple_range_request or
                (self.is_storlet_range_request and self.execute_on_proxy))

    def is_slo_response(self, resp):
        """
        Determins whether the response is a slo one

        :param resp: swob.Response instance
        :return: Whenther the response is a slo one
        """
        self.logger.debug(
            'Verify if {0}/{1}/{2} is an SLO assembly object'.format(
                self.account, self.container, self.obj))
        is_slo = 'X-Static-Large-Object' in resp.headers
        if is_slo:
            self.logger.debug(
                '{0}/{1}/{2} is indeed an SLO assembly '
                'object'.format(self.account, self.container, self.obj))
        else:
            self.logger.debug(
                '{0}/{1}/{2} is NOT an SLO assembly object'.format(
                    self.account, self.container, self.obj))
        return is_slo

    def _update_storlet_parameters_from_headers(self):
        """
        Extract parameters for header (an alternative to parmeters through
        the query string)

        """
        parameters = {}
        for param in self.request.headers:
            if param.lower().startswith('x-storlet-parameter'):
                keyvalue = self.request.headers[param]
                keyvalue = urllib.unquote(keyvalue)
                [key, value] = keyvalue.split(':')
                parameters[key] = value
        self.request.params.update(parameters)

    def _set_metadata_in_headers(self, headers, user_metadata):
        if user_metadata:
            for key, val in user_metadata.iteritems():
                headers['X-Object-Meta-%s' % key] = val

    def _call_gateway(self, resp):
        """
        Call gateway module to get result of storlet execution
        in GET flow

        :param resp: swob.Response instance
        """
        raise NotImplementedError()

    def apply_storlet(self, resp):
        """
        Apply storlet on response

        :param resp: swob.Response instance
        :return: processed reponse
        """
        sresp = self._call_gateway(resp)

        new_headers = resp.headers.copy()

        if 'Content-Length' in new_headers:
            new_headers.pop('Content-Length')
        if 'Transfer-Encoding' in new_headers:
            new_headers.pop('Transfer-Encoding')

        # Range response(206) should be replaced by 200
        # If the range is being processed on the object node
        # then we will get 200 as the response will not have a
        # range iter.
        if 'Content-Range' in resp.headers:
            new_headers['Storlet-Input-Range'] = resp.headers['Content-Range']
            new_headers.pop('Content-Range')

        self._set_metadata_in_headers(new_headers, sresp.user_metadata)

        return Response(headers=new_headers, app_iter=sresp.data_iter,
                        reuqest=self.request)

    def _get_user_metadata(self, headers):
        metadata = {}
        for key in headers:
            if key.startswith('X-Object-Meta-Storlet'):
                pass
            elif key.startswith('X-Object-Meta-'):
                short_key = key[len('X-Object-Meta-'):]
                metadata[short_key] = headers[key]
        return metadata

    def _get_storlet_invocation_options(self, req):
        options = dict()

        filtered_key = ['X-Storlet-Range', 'X-Storlet-Generate-Log']

        for key in req.headers:
            prefix = 'X-Storlet-'
            if key.startswith(prefix) and key not in filtered_key:
                new_key = 'storlet_' + \
                    key[len(prefix):].lower().replace('-', '_')
                options[new_key] = req.headers.get(key)

        scope = self.account
        if scope.rfind(':') > 0:
            scope = scope[:scope.rfind(':')]
        options['scope'] = scope

        options['generate_log'] = \
            config_true_value(req.headers.get('X-Storlet-Generate-Log'))

        options['file_manager'] = \
            SwiftFileManager(self.account, self.storlet_container,
                             self.storlet_dependency, self.log_container,
                             self.client_conf_file, self.logger)

        return options

    def _build_storlet_request(self, req, sheaders, sbody_iter):
        """
        Build a storlet_gatway.common.stob.StorletRequest (or its child)
        instance for storlet invocation

        :param req: an instane of swift.common.swob.Request
        :param sheaders: swift.common.swob.HeaderKeyDict instance which
                         includes object metadata information to be passed
                         to storlet daemon
        :param sbody_iter: an iterator instance to pass to storlet daemon as
                           input stream which can have _fp to suggest fd to
                           read directly.
        :return: storlet_gatway.common.stob.StorletRequest instance (or its
                 child instance)
        """
        storlet_id = req.headers.get('X-Run-Storlet')
        user_metadata = self._get_user_metadata(sheaders)
        options = self._get_storlet_invocation_options(req)

        if hasattr(sbody_iter, '_fp'):
            sreq = self.sreq_class(storlet_id, req.params, user_metadata,
                                   data_fd=sbody_iter._fp.fileno(),
                                   options=options)
        else:
            sreq = self.sreq_class(storlet_id, req.params, user_metadata,
                                   sbody_iter, options=options)
        return sreq
