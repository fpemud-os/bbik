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
from .util import Util


class BootEntry:

    @staticmethod
    def new_from_postfix(bbki, postfix, history_entry=False):
        # postfix example: x86_64-3.9.11-gentoo-r1
        partList = postfix.split("-")
        if len(partList) < 2:
            raise ValueError("illegal postfix")
        if not Util.isValidKernelArch(partList[0]):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal postfix")
        if not Util.isValidKernelVer(partList[1]):          # FIXME: isValidKernelVer should be moved out from util
            raise ValueError("illegal postfix")

        arch = partList[0]
        verstr = "-".join(partList[1:])
        return BootEntry(bbki, arch, verstr, history_entry)

    @staticmethod
    def new_from_verstr(bbki, arch, verstr, history_entry=False):
        if arch == "native":
            arch = os.uname().machine
        if not Util.isValidKernelArch(arch):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal arch")

        # verstr example: 3.9.11-gentoo-r1
        partList = verstr.split("-")
        if len(partList) < 1:
            raise ValueError("illegal verstr")
        if not Util.isValidKernelVer(partList[0]):          # FIXME: isValidKernelVer should be moved out from util
            raise ValueError("illegal verstr")

        return BootEntry(bbki, arch, verstr, history_entry)

    @staticmethod
    def new_from_kernel_srcdir(bbki, arch, kernel_srcdir, history_entry=False):
        if arch == "native":
            arch = os.uname().machine
        if not Util.isValidKernelArch(arch):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal arch")

        version = None
        patchlevel = None
        sublevel = None
        extraversion = None
        with open(os.path.join(kernel_srcdir, "Makefile")) as f:
            buf = f.read()

            m = re.search("VERSION = ([0-9]+)", buf, re.M)
            if m is None:
                raise ValueError("illegal kernel source directory")
            version = int(m.group(1))

            m = re.search("PATCHLEVEL = ([0-9]+)", buf, re.M)
            if m is None:
                raise ValueError("illegal kernel source directory")
            patchlevel = int(m.group(1))

            m = re.search("SUBLEVEL = ([0-9]+)", buf, re.M)
            if m is None:
                raise ValueError("illegal kernel source directory")
            sublevel = int(m.group(1))

            m = re.search("EXTRAVERSION = (\\S+)", buf, re.M)
            if m is not None:
                extraversion = m.group(1)

        if extraversion is not None:
            verstr = "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
        else:
            verstr = "%d.%d.%d" % (version, patchlevel, sublevel)
        return BootEntry(bbki, arch, verstr, history_entry)

    def __init__(self, bbki, arch, verstr, history_entry=False):
        self._bbki = bbki
        self._arch = arch
        self._verstr = verstr
        if not history_entry:
            self._bootDir = self._bbki._fsLayout.get_boot_dir()
        else:
            self._bootDir = self._bbki._fsLayout.get_boot_history_dir()

    @property
    def postfix(self):
        # string, eg: "x86_64-3.9.11-gentoo-r1"
        return self._arch + "-" + self._verstr

    @property
    def arch(self):
        # string, eg: "x86_64"
        return self._arch

    @property
    def verstr(self):
        # string, eg: "3.9.11-gentoo-r1"
        return self._verstr

    @property
    def ver(self):
        # string, eg: "3.9.11"
        try:
            return self._verstr[:self._verstr.index("-")]
        except ValueError:
            return self._verstr

    @property
    def kernel_filename(self):
        # string, eg: "kernel-x86_64-3.9.11-gentoo-r1"
        return "kernel-" + self._kernelTarget.postfix

    @property
    def kernel_filepath(self):
        # string, eg: "/boot/kernel-x86_64-3.9.11-gentoo-r1"
        return os.path.join(self._bootDir, self.kernel_filename)

    @property
    def kernel_config_filename(self):
        # string, eg: "config-x86_64-3.9.11-gentoo-r1"
        return "config-"+ self._kernelTarget.postfix

    @property
    def kernel_config_filepath(self):
        # string, eg: "/boot/config-x86_64-3.9.11-gentoo-r1"
        return os.path.join(self._bootDir, self.kernel_config_filename)

    @property
    def kernel_config_rules_filename(self):
        # string, eg: "config-x86_64-3.9.11-gentoo-r1.rules"
        return "config-" + self._kernelTarget.postfix + ".rules"

    @property
    def kernel_config_rules_filepath(self):
        # string, eg: "/boot/config-x86_64-3.9.11-gentoo-r1.rules"
        return os.path.join(self._bootDir, self.kernel_config_rules_filename)

    @property
    def kernel_modules_dirpath(self):
        # string, eg: "/lib/modules/5.1.14-gentoo-r1"
        return self._bbki._fsLayout.get_kernel_modules_dir(self._verstr)

    @property
    def initrd_filename(self):
        # string, eg: "initramfs-x86_64-3.9.11-gentoo-r1"
        return "initramfs-" + self._kernelTarget.postfix

    @property
    def initrd_filepath(self):
        # string, eg: "/boot/initramfs-x86_64-3.9.11-gentoo-r1"
        return os.path.join(self._bootDir, self.initrd_filename)

    @property
    def initrd_tar_filename(self):
        # string, eg: "initramfs-x86_64-3.9.11-gentoo-r1.tar.bz2"
        return "initramfs-files-" + self._kernelTarget.postfix + ".tar.bz2"

    @property
    def initrd_tar_filepath(self):
        # string, eg: "/boot/initramfs-x86_64-3.9.11-gentoo-r1.tar.bz2"
        return os.path.join(self._bootDir, self.initrd_tar_filename)

    def has_kernel_files(self):
        if not os.path.exists(self.kernel_filepath):
            return False
        if not os.path.exists(self.kernel_config_filepath):
            return False
        if not os.path.exists(self.kernel_config_rules_filepath):
            return False
        if not os.path.exists(self._bbki._fsLayout.get_kernel_modules_dir(self._verstr)):
            return False
        return True

    def has_initrd_files(self):
        if not os.path.exists(self.initrd_filepath):
            return False
        if not os.path.exists(self.initrd_tar_filepath):
            return False
        return True

    def ___eq___(self, other):
        return self._bbki == other._bbki and self._kernelTarget == other._kernelInfo and self._bootDir == other._bootDir
