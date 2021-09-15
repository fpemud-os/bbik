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


from ._util import Util
from ._util import SystemMounts


class BootDirWriter:

    def __init__(self, bbki):
        self._bbki = bbki
        self._refcount = 0              # support nesting
        self._remounted = False

    def start(self):
        while self._refcount == 0:
            # check if remount-boot-rw is allowed
            if not self._bbki.config.get_remount_boot_rw():
                break

            # find and check mount point for /boot
            entry = SystemMounts().find_entry_by_mount_point(self._bbki._fsLayout.get_boot_dir())
            if entry is None or "rw" in entry.mnt_opts:
                break

            # remount as rw
            Util.cmdCall("/bin/mount", self._bbki._fsLayout.get_boot_dir(), "-o", "rw,remount")
            self._remounted = True
            break

        self._refcount += 1

    def end(self):
        assert self._refcount >= 0
        try:
            if self._refcount == 1 and self._remounted:
                # remount as ro
                Util.cmdCall("/bin/mount", self._bbki._fsLayout.get_boot_dir(), "-o", "ro,remount")
                self._remounted = False
        finally:
            self._refcount -= 1

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.end()
