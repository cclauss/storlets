"""-------------------------------------------------------------------------
Copyright IBM Corp. 2015, 2015 All Rights Reserved
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
Limitations under the License.
-------------------------------------------------------------------------"""

import os
from contextlib import contextmanager
from eventlet import Timeout


# TODO(takashi): Move the following modules under storlet_gateway
class StorletRuntimeException(Exception):
    pass


class StorletTimeout(Timeout, StorletRuntimeException):
    pass


class StorletConfigError(Exception):
    pass


class StorletLogger(object):
    def __init__(self, path, name):
        self.full_path = os.path.join(path, '%s.log' % name)

    def open(self):
        self._file = open(self.full_path, 'a')

    def getfd(self):
        return self._file.fileno()

    def getsize(self):
        statinfo = os.stat(self.full_path)
        return statinfo.st_size

    def close(self):
        self._file.close()

    @contextmanager
    def activate(self):
        self.open()
        yield
        self.close()
