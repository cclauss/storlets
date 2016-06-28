# Copyright (c) 2010-2015 OpenStack Foundation
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

import mock
import unittest

from contextlib import contextmanager
from swift.common.swob import Request, HTTPOk, HTTPCreated, HTTPAccepted, \
    HTTPBadRequest, HTTPNotFound
from storlet_middleware.handlers import StorletProxyHandler

from tests.unit.swift.storlet_middleware.handlers import \
    BaseTestStorletMiddleware


@contextmanager
def fake_acc_info(acc_info):
    with mock.patch('storlet_middleware.handlers.proxy.'
                    'get_account_info') as ai:
        ai.return_value = acc_info
        yield


@contextmanager
def storlet_enabled():
    acc_info = {'meta': {'storlet-enabled': 'true'}}
    with fake_acc_info(acc_info):
        yield


class TestStorletMiddlewareProxy(BaseTestStorletMiddleware):
    def setUp(self):
        super(TestStorletMiddlewareProxy, self).setUp()
        self.conf['execution_server'] = 'proxy'

    def test_GET_without_storlets(self):
        def basic_get(path):
            req = Request.blank(
                path, environ={'REQUEST_METHOD': 'GET'})
            self.app.register('GET', path, HTTPOk, body='FAKE APP')
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp, ['FAKE APP'])
            self.app.reset_all()

        for target in ('AUTH_a', 'AUTH_a/c', 'AUTH_a/c/o'):
            path = '/'.join(['', 'v1', target])
            basic_get(path)

    def test_GET_with_storlets(self):
        # TODO(takashi): decide request path based on config value
        target = '/v1/AUTH_a/c/o'
        self.app.register('GET', target, HTTPOk, body='FAKE RESULT')
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, headers={},
                          body='jar binary')

        acc_info = {'meta': {'storlet-enabled': 'true'}}
        with fake_acc_info(acc_info):
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar'})
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp, ['FAKE RESULT'])

            calls = self.app.get_calls()

            # Make sure now we sent two requests to swift
            self.assertEqual(2, len(calls))

            # The first one is HEAD request to storlet object
            self.assertEqual('HEAD', calls[0][0])
            self.assertEqual(storlet, calls[0][1])

            # The last one is exexution GET call
            self.assertEqual(target, calls[-1][1])
            self.assertIn('X-Run-Storlet', calls[-1][2])

    def test_GET_with_storlets_disabled_account(self):
        target = '/v1/AUTH_a/c/o'

        acc_info = {'meta': {}}
        with fake_acc_info(acc_info):
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar'})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('400 Bad Request', self.got_statuses[-1])

            calls = self.app.get_calls()
            self.assertEqual(0, len(calls))

    def test_GET_with_storlets_object_404(self):
        target = '/v1/AUTH_a/c/o'
        self.app.register('GET', target, HTTPNotFound)
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar'})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('404 Not Found', self.got_statuses[-1])

            calls = self.app.get_calls()
            self.assertEqual(2, len(calls))

    def test_GET_with_storlets_and_http_range(self):
        target = '/v1/AUTH_a/c/o'

        with storlet_enabled():
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar',
                         'Range': 'bytes=10-20'})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('400 Bad Request', self.got_statuses[-1])

    def test_GET_with_storlets_and_storlet_range(self):
        target = '/v1/AUTH_a/c/o'
        self.app.register('GET', target, HTTPOk, body='FAKE APP')
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req_range = 'bytes=1-6'
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar',
                         'X-Storlet-Run-On-Proxy': '',
                         'X-Storlet-Range': req_range})
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp.read(), 'AKE AP')

            resp_headers = dict(self.got_headers[-1])
            self.assertFalse('Content-Range' in resp_headers)
            self.assertEqual(resp_headers['Storlet-Input-Range'],
                             'bytes 1-6/8')

            raw_req = self.app.get_calls('GET', target)[0]
            for key in ['Range', 'X-Storlet-Range']:
                self.assertEqual(raw_req[2][key], req_range)

    def test_GET_with_storlets_and_object_storlet_range(self):
        # Create a single range request that needs to be
        # processed by the object handler
        target = '/v1/AUTH_a/c/o'
        self.app.register('GET', target, HTTPOk, body='FAKE APP')
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req_range = 'bytes=1-6'
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar',
                         'X-Storlet-Range': req_range})
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            # We assert that nothing actually happens
            # by the proxy handler
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp, ['FAKE APP'])

    def test_GET_slo_without_storlets(self):
        target = '/v1/AUTH_a/c/slo_manifest'
        self.app.register('GET', target, HTTPOk,
                          headers={'x-static-large-object': 'True'},
                          body='FAKE APP')

        req = Request.blank(
            target, environ={'REQUEST_METHOD': 'GET'})
        app = self.get_app(self.app, self.conf)
        resp = app(req.environ, self.start_response)
        self.assertEqual(resp, ['FAKE APP'])

    def test_GET_slo_with_storlets(self):
        target = '/v1/AUTH_a/c/slo_manifest'
        self.app.register('GET', target, HTTPOk,
                          headers={'x-static-large-object': 'True'},
                          body='FAKE APP')
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req = Request.blank(
                target, environ={'REQUEST_METHOD': 'GET'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar'})
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp.read(), 'FAKE APP')

            calls = self.app.get_calls()
            self.assertEqual(2, len(calls))

    def test_PUT_without_storlets(self):
        def basic_put(path):
            self.app.register('PUT', path, HTTPCreated)
            req = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('201 Created', self.got_statuses[-1])
            self.app.reset_all()

        for target in ('AUTH_a', 'AUTH_a/c', 'AUTH_a/c/o'):
            path = '/'.join(['', 'v1', target])
            basic_put(path)

    def test_PUT_with_storlets(self):
        target = '/v1/AUTH_a/c/o'
        self.app.register('PUT', target, HTTPCreated)
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req = Request.blank(target, environ={'REQUEST_METHOD': 'PUT'},
                                headers={'X-Run-Storlet': 'Storlet-1.0.jar'},
                                body='FAKE APP')
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('201 Created', self.got_statuses[-1])

            calls = self.app.get_calls()
            # Make sure now we sent two requests to swift
            self.assertEqual(2, len(calls))

            # The first one is HEAD request to storlet object
            self.assertEqual('HEAD', calls[0][0])
            self.assertEqual(storlet, calls[0][1])

            # The last one is PUT request about processed object
            self.assertEqual('PUT', calls[-1][0])
            self.assertEqual(target, calls[-1][1])
            self.assertEqual(calls[-1][3], 'FAKE APP')

    def test_PUT_copy_without_storlets(self):
        target = '/v1/AUTH_a/c/to'
        copy_from = 'c/so'
        self.app.register('PUT', target, HTTPCreated)

        req = Request.blank(target, environ={'REQUEST_METHOD': 'PUT'},
                            headers={'X-Copy-From': copy_from,
                                     'X-Backend-Storage-Policy-Index': 0})
        app = self.get_app(self.app, self.conf)
        app(req.environ, self.start_response)
        self.assertEqual('201 Created', self.got_statuses[-1])

    def test_PUT_copy_with_storlets(self):
        source = '/v1/AUTH_a/c/so'
        target = '/v1/AUTH_a/c/to'
        copy_from = 'c/so'
        self.app.register('GET', source, HTTPOk, body='source body')
        self.app.register('PUT', target, HTTPCreated)
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req = Request.blank(target, environ={'REQUEST_METHOD': 'PUT'},
                                headers={'X-Copy-From': copy_from,
                                         'X-Run-Storlet': 'Storlet-1.0.jar',
                                         'X-Backend-Storage-Policy-Index': 0})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('201 Created', self.got_statuses[-1])
            get_calls = self.app.get_calls('GET', source)
            self.assertEqual(len(get_calls), 1)
            self.assertEqual(get_calls[-1][3], '')
            self.assertEqual(get_calls[-1][1], source)
            put_calls = self.app.get_calls('PUT', target)
            self.assertEqual(len(put_calls), 1)
            self.assertEqual(put_calls[-1][3], 'source body')

    def test_COPY_verb_without_storlets(self):
        source = '/v1/AUTH_a/c/so'
        destination = 'c/to'
        self.app.register('COPY', source, HTTPCreated)

        req = Request.blank(source, environ={'REQUEST_METHOD': 'COPY'},
                            headers={'Destination': destination,
                                     'X-Backend-Storage-Policy-Index': 0})
        app = self.get_app(self.app, self.conf)
        app(req.environ, self.start_response)
        self.assertEqual('201 Created', self.got_statuses[-1])

    def test_COPY_verb_with_storlets(self):
        source = '/v1/AUTH_a/c/so'
        target = '/v1/AUTH_a/c/to'
        destination = 'c/to'
        self.app.register('GET', source, HTTPOk, body='source body')
        self.app.register('PUT', target, HTTPCreated)
        storlet = '/v1/AUTH_a/storlet/Storlet-1.0.jar'
        self.app.register('GET', storlet, HTTPOk, body='jar binary')

        with storlet_enabled():
            req = Request.blank(source, environ={'REQUEST_METHOD': 'COPY'},
                                headers={'Destination': destination,
                                         'X-Run-Storlet': 'Storlet-1.0.jar',
                                         'X-Backend-Storage-Policy-Index': 0})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('201 Created', self.got_statuses[-1])
            get_calls = self.app.get_calls('GET', source)
            self.assertEqual(len(get_calls), 1)
            self.assertEqual(get_calls[-1][3], '')
            self.assertEqual(get_calls[-1][1], source)
            put_calls = self.app.get_calls('PUT', target)
            self.assertEqual(len(put_calls), 1)
            self.assertEqual(put_calls[-1][3], 'source body')

    def test_copy_with_unsupported_headers(self):
        target = '/v1/AUTH_a/c/o'

        def copy(method, copy_header):
            base_headers = {'X-Run-Storlet': 'Storlet-1.0.jar',
                            'X-Backend-Storage-Policy-Index': 0}
            base_headers.update(copy_header)
            req = Request.blank(target, environ={'REQUEST_METHOD': method},
                                headers=base_headers)
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)

        with storlet_enabled():
            self.assertRaises(HTTPBadRequest,
                              copy('COPY', {'Destination-Account': 'a'}))
            self.assertRaises(HTTPBadRequest,
                              copy('COPY', {'x-fresh-metadata': ''}))
            self.assertRaises(HTTPBadRequest,
                              copy('PUT', {'X-Copy-From-Account': 'a'}))
            self.assertRaises(HTTPBadRequest,
                              copy('PUT', {'x-fresh-metadata': ''}))

    def test_PUT_storlet(self):
        target = '/v1/AUTH_a/storlet/storlet-1.0.jar'
        self.app.register('PUT', target, HTTPCreated)

        with storlet_enabled():
            sheaders = {'X-Object-Meta-Storlet-Language': 'Java',
                        'X-Object-Meta-Storlet-Interface-Version': '1.0',
                        'X-Object-Meta-Storlet-Dependency': 'dependency',
                        'X-Object-Meta-Storlet-Main':
                            'org.openstack.storlet.Storlet'}
            req = Request.blank(target, environ={'REQUEST_METHOD': 'PUT'},
                                headers=sheaders)
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('201 Created', self.got_statuses[-1])

    def test_PUT_storlet_mandatory_parameter_fails(self):
        target = '/v1/AUTH_a/storlet/storlet-1.0.jar'
        self.app.register('PUT', target, HTTPCreated)

        drop_headers = [
            ('X-Object-Meta-Storlet-Language', 'Language'),
            ('X-Object-Meta-Storlet-Interface-Version', 'Interface-Version'),
            ('X-Object-Meta-Storlet-Dependency', 'Dependency'),
            ('X-Object-Meta-Storlet-Main', 'Main'),
        ]

        def put(path, header, assertion):
            sheaders = {'X-Object-Meta-Storlet-Language': 'Java',
                        'X-Object-Meta-Storlet-Interface-Version': '1.0',
                        'X-Object-Meta-Storlet-Dependency': 'dependency',
                        'X-Object-Meta-Storlet-Main':
                            'org.openstack.storlet.Storlet'}
            del sheaders[header]
            req = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'},
                                headers=sheaders)
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            # FIXME(kota_): Unfortunately, we can not test yet here because
            # the validation is not in stub gateway but in docker gateway so
            # need more refactor to parse the functionality to be easy testing
            # self.assertEqual('400 BadRequest', self.got_statuses[-1])

        for header, assertion in drop_headers:
            with storlet_enabled():
                put(target, header, assertion)

    def test_POST_storlet(self):
        target = '/v1/AUTH_a/storlet/storlet-1.0.jar'
        self.app.register('POST', target, HTTPAccepted)

        with storlet_enabled():
            sheaders = {'X-Object-Meta-Storlet-Language': 'Java',
                        'X-Object-Meta-Storlet-Interface-Version': '1.0',
                        'X-Object-Meta-Storlet-Dependency': 'dependency',
                        'X-Object-Meta-Storlet-Main':
                            'org.openstack.storlet.Storlet'}
            req = Request.blank(target, environ={'REQUEST_METHOD': 'POST'},
                                headers=sheaders)
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('202 Accepted', self.got_statuses[-1])

    def test_GET_storlet(self):
        target = '/v1/AUTH_a/storlet/storlet-1.0.jar'
        sheaders = {'X-Object-Meta-Storlet-Language': 'Java',
                    'X-Object-Meta-Storlet-Interface-Version': '1.0',
                    'X-Object-Meta-Storlet-Dependency': 'dependency',
                    'X-Object-Meta-Storlet-Main':
                        'org.openstack.storlet.Storlet'}
        self.app.register('GET', target, HTTPOk, headers=sheaders,
                          body='jar binary')

        with storlet_enabled():
            req = Request.blank(target, environ={'REQUEST_METHOD': 'GET'})
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp, ['jar binary'])
            resp_headers = dict(self.got_headers[-1])
            for key in sheaders:
                self.assertEqual(resp_headers[key], sheaders[key])

    def test_PUT_dependency(self):
        target = '/v1/AUTH_a/dependency/dependency'
        self.app.register('PUT', target, HTTPCreated)

        with storlet_enabled():
            sheaders = {'X-Object-Meta-Storlet-Dependency-Version': '1',
                        'X-Object-Meta-Storlet-Dependency-Permissions': '0755'}
            req = Request.blank(target, environ={'REQUEST_METHOD': 'PUT'},
                                headers=sheaders)
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('201 Created', self.got_statuses[-1])

    def test_POST_dependency(self):
        target = '/v1/AUTH_a/dependency/dependency'
        self.app.register('POST', target, HTTPAccepted)

        with storlet_enabled():
            sheaders = {'X-Object-Meta-Storlet-Dependency-Version': '1',
                        'X-Object-Meta-Storlet-Dependency-Permissions': '0755'}
            req = Request.blank(target, environ={'REQUEST_METHOD': 'POST'},
                                headers=sheaders)
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('202 Accepted', self.got_statuses[-1])

    def test_GET_dependency(self):
        target = '/v1/AUTH_a/dependency/dependency'
        sheaders = {'X-Object-Meta-Storlet-Dependency-Version': '1',
                    'X-Object-Meta-Storlet-Dependency-Permissions': '0755'}
        self.app.register('GET', target, HTTPOk, headers=sheaders,
                          body='FAKE APP')

        with storlet_enabled():
            req = Request.blank(target, environ={'REQUEST_METHOD': 'GET'})
            app = self.get_app(self.app, self.conf)
            resp = app(req.environ, self.start_response)
            self.assertEqual('200 OK', self.got_statuses[-1])
            self.assertEqual(resp, ['FAKE APP'])
            resp_headers = dict(self.got_headers[-1])
            for key in sheaders:
                self.assertEqual(resp_headers[key], sheaders[key])

    def test_storlets_with_invalid_method(self):
        with storlet_enabled():
            req = Request.blank(
                '/v1/AUTH_a/c/o', environ={'REQUEST_METHOD': '_parse_vaco'},
                headers={'X-Run-Storlet': 'Storlet-1.0.jar'})
            app = self.get_app(self.app, self.conf)
            app(req.environ, self.start_response)
            self.assertEqual('405 Method Not Allowed', self.got_statuses[-1])


class TestStorletProxyHandler(unittest.TestCase):
    def setUp(self):
        self.handler_class = StorletProxyHandler

    def test_init_handler(self):
        req = Request.blank(
            '/v1/acc/cont/obj', environ={'REQUEST_METHOD': 'GET'},
            headers={'X-Backend-Storlet-Policy-Index': '0',
                     'X-Run-Storlet': 'Storlet-1.0.jar'})
        with storlet_enabled():
            handler = self.handler_class(
                req, mock.MagicMock(), mock.MagicMock(), mock.MagicMock())

        self.assertEqual('/v1/acc/cont/obj', handler.request.path)
        self.assertEqual('v1', handler.api_version)
        self.assertEqual('acc', handler.account)
        self.assertEqual('cont', handler.container)
        self.assertEqual('obj', handler.obj)

        # overwrite the request
        # TODO(kota_): is it good to raise an error immediately?
        #              or re-validate the req again?
        req = Request.blank(
            '/v2/acc2/cont2/obj2', environ={'REQUEST_METHOD': 'GET'},
            headers={'X-Backend-Storlet-Policy-Index': '0',
                     'X-Run-Storlet': 'Storlet-1.0.jar'})
        handler.request = req
        self.assertEqual('/v2/acc2/cont2/obj2', handler.request.path)
        self.assertEqual('v2', handler.api_version)
        self.assertEqual('acc2', handler.account)
        self.assertEqual('cont2', handler.container)
        self.assertEqual('obj2', handler.obj)

        # no direct assignment allowed
        with self.assertRaises(AttributeError):
            handler.api_version = '1'

        with self.assertRaises(AttributeError):
            handler.account = 'acc'

        with self.assertRaises(AttributeError):
            handler.container = 'cont'

        with self.assertRaises(AttributeError):
            handler.obj = 'obj'


if __name__ == '__main__':
    unittest.main()
