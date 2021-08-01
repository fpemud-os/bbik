#!/usr/bin/env python3

# Copyright (c) 2005-2014 Fpemud <fpemud@sina.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import time
import robust_layer


class Temp:

    def sync_kernel_info(self):
        # get kernel version from internet
        while True:
            ver = self._findKernelVersion("stable")
            if ver is not None:
                self._writeKsyncFile("kernel", ver)
                break
            time.sleep(robust_layer.RETRY_TIMEOUT)
        return self.getLatestKernelVersion()


    def sync_firmware_info(self):
        # get firmware version version from internet
        while True:
            ver = self._findFirmwareVersion()
            if ver is not None:
                self._writeKsyncFile("firmware", ver)
                break
            time.sleep(robust_layer.RETRY_TIMEOUT)
        return self.getLatestFirmwareVersion()

    def sync_wireless_regdb_info(self):
        # get wireless-regulatory-database version from internet
        while True:
            ver = self._findWirelessRegDbVersion()
            if ver is not None:
                self._writeKsyncFile("wireless-regdb", ver)
                break
            time.sleep(robust_layer.RETRY_TIMEOUT)
        return self.getLatestWirelessRegDbVersion()

    def _findKernelVersion(self, typename):
        try:
            with urllib.request.urlopen(self.kernelUrl, timeout=robust_layer.TIMEOUT) as resp:
                if resp.info().get('Content-Encoding') is None:
                    fakef = resp
                elif resp.info().get('Content-Encoding') == 'gzip':
                    fakef = io.BytesIO(resp.read())
                    fakef = gzip.GzipFile(fileobj=fakef)
                else:
                    assert False
                root = lxml.html.parse(fakef)

                td = root.xpath(".//td[text()='%s:']" % (typename))[0]
                td = td.getnext()
                while len(td) > 0:
                    td = td[0]
                return td.text
        except OSError as e:
            print("Failed to acces %s, %s" % (self.kernelUrl, e))
            return None

    def _findFirmwareVersion(self):
        try:
            ret = None
            with urllib.request.urlopen(self.firmwareUrl, timeout=robust_layer.TIMEOUT) as resp:
                root = lxml.html.parse(resp)
                for atag in root.xpath(".//a"):
                    m = re.fullmatch("linux-firmware-(.*)\\.tar\\.xz", atag.text)
                    if m is not None:
                        if ret is None or ret < m.group(1):
                            ret = m.group(1)
                assert ret is not None
            return ret
        except OSError as e:
            print("Failed to acces %s, %s" % (self.firmwareUrl, e))
            return None

    def _findWirelessRegDbVersion(self):
        try:
            ver = None
            with urllib.request.urlopen(self.wirelessRegDbDirUrl, timeout=robust_layer.TIMEOUT) as resp:
                out = resp.read().decode("iso8859-1")
                for m in re.finditer("wireless-regdb-([0-9]+\\.[0-9]+\\.[0-9]+)\\.tar\\.xz", out, re.M):
                    if ver is None or m.group(1) > ver:
                        ver = m.group(1)
            return ver
        except OSError as e:
            print("Failed to acces %s, %s" % (self.wirelessRegDbDirUrl, e))
            return None

    def _writeKsyncFile(self, key, *kargs):
        vlist = ["", "", "", ""]
        if os.path.exists(self.ksyncFile):
            with open(self.ksyncFile) as f:
                vlist = f.read().split("\n")[0:3]
                while len(vlist) < 4:
                    vlist.append("")

        if key == "kernel":
            vlist[0] = kargs[0]
        elif key == "firmware":
            vlist[1] = kargs[0]
        elif key == "wireless-regdb":
            vlist[2] = kargs[0]

        with open(self.ksyncFile, "w") as f:
            for v in vlist:
                f.write(v + "\n")
