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
from six import StringIO

from swift.common.swob import Request
from storlet_gateway.common.exceptions import FileManagementError
from storlet_middleware.handlers import StorletBaseHandler
from storlet_middleware.handlers.base import SwiftFileManager
from tests.unit.swift import FakeLogger


class TestSwiftFileManager(unittest.TestCase):
    def setUp(self):
        self.logger = FakeLogger()
        self.manager = SwiftFileManager('a', 'storlet', 'dependency', 'log',
                                        'client.conf', self.logger)

    @contextmanager
    def _mock_internal_client(self, cls):
        with mock.patch('storlet_middleware.handlers.base.InternalClient',
                        cls):
            yield

    def test_get_storlet(self):
        name = 'Storlet-1.0.jar'

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def get_object(self, account, container, obj, headers,
                           acceptable_statuses=None):
                return '200', {}, StringIO('test')

        with self._mock_internal_client(DummyClient):
            data_iter, perm = self.manager.get_storlet(name)
            self.assertEqual('test', next(data_iter))
            self.assertIsNone(perm)

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def get_object(self, account, container, obj, headers,
                           acceptable_statuses=None):
                raise Exception('Some error')

        with self._mock_internal_client(DummyClient):
            with self.assertRaises(FileManagementError):
                self.manager.get_storlet(name)

    def test_get_dependency(self):
        name = 'depfile'

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def get_object(self, account, container, obj, headers,
                           acceptable_statuses=None):
                headers = {'X-Object-Meta-Storlet-Dependency-Permissions':
                           '0600'}
                return '200', headers, StringIO('test')

        with self._mock_internal_client(DummyClient):
            data_iter, perm = self.manager.get_dependency(name)
            self.assertEqual('test', next(data_iter))
            self.assertEqual('0600', perm)

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def get_object(self, account, container, obj, headers,
                           acceptable_statuses=None):
                return '200', {}, StringIO('test')

        with self._mock_internal_client(DummyClient):
            data_iter, perm = self.manager.get_dependency(name)
            self.assertEqual('test', next(data_iter))
            self.assertIsNone(perm)

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def get_object(self, account, container, obj, headers,
                           acceptable_statuses=None):
                raise Exception('Some error')

        with self._mock_internal_client(DummyClient):
            with self.assertRaises(FileManagementError):
                self.manager.get_dependency(name)

    def test_put_log(self):
        name = 'logfile'

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def upload_object(self, fobj, account, container, obj,
                              headers=None):
                pass

        with self._mock_internal_client(DummyClient):
            self.manager.put_log(name, mock.MagicMock())

        class DummyClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def upload_object(self, fobj, account, container, obj,
                              headers=None):
                raise Exception('Some error')

        with self._mock_internal_client(DummyClient):
            with self.assertRaises(FileManagementError):
                self.manager.put_log(name, mock.MagicMock())


class TestStorletBaseHandler(unittest.TestCase):
    def test_init_failed_via_base_handler(self):
        def assert_not_implemented(method, path, headers):
            req = Request.blank(
                path, environ={'REQUEST_METHOD': method},
                headers=headers)
            try:
                StorletBaseHandler(
                    req, mock.MagicMock(), mock.MagicMock(), mock.MagicMock())
            except NotImplementedError:
                pass
            except Exception as e:
                self.fail('Unexpected Error: %s raised with %s, %s, %s' %
                          (repr(e), path, method, headers))

        for method in ('PUT', 'GET', 'POST'):
            for path in ('', '/v1', '/v1/a', '/v1/a/c', '/v1/a/c/o'):
                for headers in ({}, {'X-Run-Storlet': 'Storlet-1.0.jar'}):
                    assert_not_implemented(method, path, headers)


if __name__ == '__main__':
    unittest.main()
