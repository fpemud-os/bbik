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


import os
import re
from . import util


class Config:

    def __init__(self, cfgdir=None):
        if cfgdir is None:
            cfgdir = "/etc/bbki"

        self._cfgKernelMaskDir = os.path.join(cfgdir, "kernel.mask")
        self._cfgKernelUseDir = os.path.join(cfgdir, "kernel.use")

        self._dataDir = "/var/lib/bbki"
        self._dataRepoDir = os.path.join(self._dataDir, "repo")

        self._cacheDir = "/var/cache/bbki"
        self._cacheDistfilesDir = os.path.join(self._cacheDir, "distfiles")
        self._cacheDistfilesRoDirList = []

    @property
    def data_repo_dir(self):
        return self._dataRepoDir

    @property
    def cache_distfiles_dir(self):
        return self._cacheDistfilesDir

    @property
    def cache_distfiles_ro_dir_list(self):
        return self._cacheDistfilesRoDirList

    def check_version_mask(self, version_type, version):
        assert version_type in ["kernel", "firmware", "wireless-regdb"]

        for fn in os.listdir(self._cfgKernelMaskDir):
            with open(os.path.join(self._cfgKernelMaskDir, fn), "r") as f:
                buf = f.read()
                m = re.search("^>%s-(.*)$" % (version_type), buf, re.M)
                if m is not None:
                    if version > m.group(1):
                        version = m.group(1)
        return version

    def get_kernel_use_flags(self):
        """returns list of USE flags"""

        ret = set()
        for fn in os.listdir(self.kernelUseDir):
            for line in util.readListFile(os.path.join(self.kernelUseDir, fn)):
                line = line.replace("\t", " ")
                line2 = ""
                while line2 != line:
                    line2 = line
                    line = line.replace("  ", " ")
                for item in line.split(" "):
                    if item.startswith("-"):
                        item = item[1:]
                        ret.remove(item)
                    else:
                        ret.add(item)
        return sorted(list(ret))
