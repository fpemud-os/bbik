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
from . import Bbki


class Config:

    def __init__(self, cfgdir=None):
        if cfgdir is None:
            cfgdir = "/etc/bbki"

        self._cfgBbkiKernelTypeFile = os.path.join(cfgdir, "bbki.kernel_type")
        self._cfgBbkiKernelAddonDir = os.path.join(cfgdir, "bbki.kernel_addon")
        self._cfgBbkiMaskDir = os.path.join(cfgdir, "bbki.mask")

        self._dataDir = "/var/lib/bbki"
        self._dataRepoDir = os.path.join(self._dataDir, "repo")

        self._cacheDir = "/var/cache/bbki"
        self._cacheDistfilesDir = os.path.join(self._cacheDir, "distfiles")
        self._cacheDistfilesRoDirList = []

        self._tmpKernelType = None
        self._tmpKernelAddonNameList = None
        self._tmpMaskBufList = None

    @property
    def data_repo_dir(self):
        return self._dataRepoDir

    @property
    def cache_distfiles_dir(self):
        return self._cacheDistfilesDir

    @property
    def cache_distfiles_ro_dir_list(self):
        return self._cacheDistfilesRoDirList

    def get_kernel_type(self):
        # fill cache
        if self._tmpKernelType is None:
            ret = util.readListFile(self._cfgBbkiKernelTypeFile)
            if len(ret) > 0:
                self._tmpKernelType = ret[0]

        # return value according to cache
        if self._tmpKernelType is None:
                raise InvalidConfigError("no kernel type specified")
        if self._tmpKernelType not in [Bbki.KERNEL_TYPE_LINUX]:
            raise InvalidConfigError("invalid kernel type \"%s\" specified" % (self._tmpKernelType))
        return self._tmpKernelType

    def get_kernel_addon_names(self):
        # fill cache
        if self._tmpKernelAddonNameList is None:
            ret = set()
            for fn in os.listdir(self._cfgBbkiKernelAddonDir):
                for line in util.readListFile(os.path.join(self._cfgBbkiKernelAddonDir, fn)):
                    ret.add(line)
            self._tmpKernelAddonNameList = sorted(list(ret))

        # return value according to cache
        return self._tmpKernelAddonNameList

    def check_version_mask(self, item_fullname, item_verstr):
        # fill cache
        if self._tmpMaskBufList is None:
            self._tmpMaskBufList = []
            for fn in os.listdir(self._cfgBbkiMaskDir):
                with open(os.path.join(self._cfgBbkiMaskDir, fn), "r") as f:
                    self._tmpMaskBufList.append(f.read())

        # match according to cache
        for buf in self._tmpMaskBufList:
            m = re.search("^>%s-(.*)$" % (item_fullname), buf, re.M)
            if m is not None:
                if util.compareVerstr(verstr, m.group(1)) > 0:
                    return False
        return True


class InvalidConfigError(Exception):

    def __init__(self, message):
        self.message = message
