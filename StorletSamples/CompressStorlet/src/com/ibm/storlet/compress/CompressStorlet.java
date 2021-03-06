/*----------------------------------------------------------------------------
 * Copyright IBM Corp. 2015, 2015 All Rights Reserved
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

/*============================================================================
 07-Jan-2016    cdoron     Initial implementation.
 ===========================================================================*/

package com.ibm.storlet.compress;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.GZIPInputStream;

import com.ibm.storlet.common.IStorlet;
import com.ibm.storlet.common.StorletException;
import com.ibm.storlet.common.StorletInputStream;
import com.ibm.storlet.common.StorletLogger;
import com.ibm.storlet.common.StorletObjectOutputStream;
import com.ibm.storlet.common.StorletContainerHandle;
import com.ibm.storlet.common.StorletOutputStream;
import com.ibm.storlet.common.StorletUtils;

public class CompressStorlet implements IStorlet {
	@Override
	public void invoke(ArrayList<StorletInputStream> inputStreams,
			ArrayList<StorletOutputStream> outputStreams,
			Map<String, String> parameters, StorletLogger log)
			throws StorletException {
		log.emitLog("CompressStorlet Invoked");

		StorletInputStream sis = inputStreams.get(0);
		InputStream is = sis.getStream();
		HashMap<String, String> metadata = sis.getMetadata();

		final int COMPRESS = 0;
		final int UNCOMPRESS = 1;

		int action = COMPRESS;
		/*
		 * Get optional action flag
		 */
                String action_str = parameters.get("action");
		if (action_str != null && action_str.equals("uncompress"))
		{
			action = UNCOMPRESS;
		}

		StorletObjectOutputStream storletObjectOutputStream = (StorletObjectOutputStream)outputStreams.get(0);
		storletObjectOutputStream.setMetadata(metadata);
		OutputStream outputStream = storletObjectOutputStream.getStream();
		try {
			byte[] buffer = new byte[65536];
			int len;
			if (action == COMPRESS) {
				GZIPOutputStream gzipOS = new GZIPOutputStream(outputStream);
				while((len=is.read(buffer)) != -1) {
					gzipOS.write(buffer, 0, len);
				}
				gzipOS.close();
			} else {
				GZIPInputStream gzipIS = new GZIPInputStream(is);
				while((len = gzipIS.read(buffer)) != -1) {
					outputStream.write(buffer, 0, len);
				}
				gzipIS.close();
			}
		} catch (IOException e) {
			log.emitLog("CompressExample - raised IOException: " + e.getMessage());
		} finally {
			try {
				is.close();
				outputStream.close();
			} catch (IOException e) {
			}
		}
		log.emitLog("CompressStorlet Invocation done");
        }
}
