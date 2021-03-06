/*----------------------------------------------------------------------------
 * Copyright (c) 2010-2016 OpenStack Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * Limitations under the License.
 * ---------------------------------------------------------------------------
 */

package com.ibm.storlet.common;

import java.io.FileDescriptor;
import java.io.InputStream;
import java.io.IOException;
import java.util.HashMap;

import com.ibm.storlet.common.RangeFileInputStream;

/**
 * A wrapper of StorletInputStream having the same interface
 * but whose inner stream is RangeFileInputStream instead of
 * java.io.InputStream
 */
public class RangeStorletInputStream extends StorletInputStream {

        public RangeStorletInputStream(FileDescriptor fd,
                                       HashMap<String, String> md,
                                       long start,
                                       long end) throws IOException {
                super(md);
                stream = (InputStream)(new RangeFileInputStream(fd, start, end));
        }
}
