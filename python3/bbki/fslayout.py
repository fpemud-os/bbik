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
from .kernel import KernelBuildTarget


class BootEntry:

    def __init__(self, build_target):
        self._buildTarget = build_target

    @property
    def build_target(self):
        return self._buildTarget

    @property
    def kernel_file(self):
        return "/boot/kernel-" + self._buildTarget.postfix

    @property
    def kernel_config_file(self):
        return "/boot/config-"+ self._buildTarget.postfix

    @property
    def kernel_config_rules_file(self):
        return "/boot/config-" + self._buildTarget.postfix + ".rules"

    # FIXME: do we really need this?
    @property
    def kernelMapFile(self):
        return "/boot/System.map-" + self._buildTarget.postfix

    # FIXME: do we really need this?
    @property
    def kernelSrcSignatureFile(self):
        return "/boot/signature-" + self._buildTarget.postfix

    @property
    def initrd_file(self):
        return "/boot/initramfs-" + self._buildTarget.postfix

    @property
    def initrd_tar_file(self):
        return "/boot/initramfs-files-" + self._buildTarget.postfix + ".tar.bz2"

    def has_kernel_files(self):
        if not os.path.exists(self.kernel_file):
            return False
        if not os.path.exists(self.kernel_config_file):
            return False
        if not os.path.exists(self.kernel_config_rules_file):
            return False
        if not os.path.exists(self.kernelMapFile):
            return False
        if not os.path.exists(self.kernelSrcSignatureFile):
            return False
        return True

    def has_initrd_files(self):
        if not os.path.exists(self.initrd_file):
            return False
        if not os.path.exists(self.initrd_tar_file):
            return False
        return True


class FsLayout:

    def get_boot_dir(self):
        return "/boot"

    def get_boot_history_dir(self):
        return "/boot/history"

    def get_kernel_modules_dir(self, build_target):
        return "/lib/modules/%s" % (build_target.verstr)

    def get_firmware_dir(self):
        return "/lib/firmware"

    def find_current_boot_entry(self, strict=True):
        ret = [x for x in sorted(os.listdir(self.get_boot_dir())) if x.startswith("kernel-")]
        if ret == []:
            return None

        buildTarget = None
        for fn in reversed(ret):
            postfix = fn[len("kernel-"):]
            try:
                buildTarget = KernelBuildTarget.new_from_postfix(postfix)
            except ValueError:
                continue

        if buildTarget is None:
            return None

        ret = BootEntry(buildTarget)
        if strict:
            if not ret.has_kernel_files():
                return None
            if not ret.has_initrd_files():
                return None
        return ret
