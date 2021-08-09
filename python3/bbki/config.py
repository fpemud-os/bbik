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
from . import Bbki
from .util import Util


class Config:

    def __init__(self, cfgdir=None):
        if cfgdir is None:
            cfgdir = "/etc/bbki"

        self._makeConf = os.path.join(cfgdir, "make.conf")

        self._profileDir = os.path.join(cfgdir, "profile")
        self._profileKernelTypeFile = os.path.join(self._profileDir, "bbki.kernel_type")
        self._profileKernelAddonDir = os.path.join(self._profileDir, "bbki.kernel_addon")
        self._profileMaskDir = os.path.join(self._profileDir, "bbki.mask")

        self._cfgKernelTypeFile = os.path.join(cfgdir, "bbki.kernel_type")
        self._cfgKernelAddonDir = os.path.join(cfgdir, "bbki.kernel_addon")
        self._cfgMaskDir = os.path.join(cfgdir, "bbki.mask")

        self._dataDir = "/var/lib/bbki"
        self._dataRepoDir = os.path.join(self._dataDir, "repo")

        self._cacheDir = "/var/cache/bbki"
        self._cacheDistfilesDir = os.path.join(self._cacheDir, "distfiles")
        self._cacheDistfilesRoDirList = []

        self._tmpDir = "/var/tmp/bbki"

        self._tKernelType = None
        self._tKernelAddonNameList = None
        self._tMaskBufList = None

    @property
    def data_repo_dir(self):
        return self._dataRepoDir

    @property
    def cache_distfiles_dir(self):
        return self._cacheDistfilesDir

    @property
    def cache_distfiles_ro_dir_list(self):
        return self._cacheDistfilesRoDirList

    @property
    def tmp_dir(self):
        return self._tmpDir

    def get_make_conf_variable(self, var_name):
        # Returns variable value, returns "" when not found
        # Multiline variable definition is not supported yet

        buf = ""
        with open(self._makeConf, 'r') as f:
            buf = f.read()

        m = re.search("^%s=\"(.*)\"$" % var_name, buf, re.MULTILINE)
        if m is None:
            return ""
        varVal = m.group(1)

        while True:
            m = re.search("\\${(\\S+)?}", varVal)
            if m is None:
                break
            varName2 = m.group(1)
            varVal2 = self.get_make_conf_variable(self._makeConf, varName2)
            if varVal2 is None:
                varVal2 = ""

            varVal = varVal.replace(m.group(0), varVal2)

        return varVal

    def get_kernel_type(self):
        # fill cache
        if self._tKernelType is None:
            if os.path.exists(self._profileKernelTypeFile):             # step1: use /etc/bbki/profile/bbki.kernel_type
                ret = Util.readListFile(self._profileKernelTypeFile)
                if len(ret) > 0:
                    self._tKernelType = ret[0]
            if os.path.exists(self._cfgKernelTypeFile):                 # step2: use /etc/bbki/bbki.kernel_type
                ret = Util.readListFile(self._cfgKernelTypeFile)
                if len(ret) > 0:
                    self._tKernelType = ret[0]

        # return value according to cache
        if self._tKernelType is None:
                raise InvalidConfigError("no kernel type specified")
        if self._tKernelType not in [Bbki.KERNEL_TYPE_LINUX]:
            raise InvalidConfigError("invalid kernel type \"%s\" specified" % (self._tKernelType))
        return self._tKernelType

    def get_kernel_addon_names(self):
        # fill cache
        if self._tKernelAddonNameList is None:
            ret = set()
            if os.path.exists(self._profileKernelAddonDir):             # step1: use /etc/bbki/profile/bbki.kernel_addon
                for fn in os.listdir(self._profileKernelAddonDir):
                    for line in Util.readListFile(os.path.join(self._profileKernelAddonDir, fn)):
                        if not line.startswith("-"):
                            ret.add(line)
                        else:
                            line = line[1:]
                            ret.remove(line)
            if os.path.exists(self._cfgKernelAddonDir):                 # step2: use /etc/bbki/bbki.kernel_addon
                for fn in os.listdir(self._cfgKernelAddonDir):
                    for line in Util.readListFile(os.path.join(self._cfgKernelAddonDir, fn)):
                        if not line.startswith("-"):
                            ret.add(line)
                        else:
                            line = line[1:]
                            ret.remove(line)
            self._tKernelAddonNameList = sorted(list(ret))

        # return value according to cache
        return self._tKernelAddonNameList

    def check_version_mask(self, item_fullname, item_verstr):
        # fill cache
        if self._tMaskBufList is None:
            self._tMaskBufList = []
            if os.path.exists(self._profileMaskDir):                 # step1: use /etc/bbki/profile/bbki.mask
                for fn in os.listdir(self._profileMaskDir):
                    with open(os.path.join(self._profileMaskDir, fn), "r") as f:
                        self._tMaskBufList.append(f.read())
            if os.path.exists(self._cfgMaskDir):                     # step2: use /etc/bbki/bbki.mask
                for fn in os.listdir(self._cfgMaskDir):
                    with open(os.path.join(self._cfgMaskDir, fn), "r") as f:
                        self._tMaskBufList.append(f.read())

        # match according to cache
        for buf in self._tMaskBufList:
            m = re.search("^>%s-(.*)$" % (item_fullname), buf, re.M)
            if m is not None:
                if Util.compareVerstr(item_verstr, m.group(1)) > 0:
                    return False
        return True


class InvalidConfigError(Exception):

    def __init__(self, message):
        self.message = message
