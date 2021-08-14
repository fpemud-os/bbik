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


class BootEntry:

    def __init__(self, bbki, kernel_info, history_entry=False):
        self._bbki = bbki
        self._kernelInfo = kernel_info
        if not history_entry:
            self._bootDir = self._bbki._fsLayout.get_boot_dir()
        else:
            self._bootDir = self._bbki._fsLayout.get_boot_history_dir()

    @property
    def arch(self):
        return self._kernelInfo.arch

    @property
    def kernel_ver(self):
        return self._kernelInfo.ver

    @property
    def kernel_verstr(self):
        return self._kernelInfo.verstr

    @property
    def kernel_filename(self):
        return "kernel-" + self._kernelInfo.postfix

    @property
    def kernel_filepath(self):
        return os.path.join(self._bootDir, self.kernel_filename)

    @property
    def kernel_config_filename(self):
        return "config-"+ self._kernelInfo.postfix

    @property
    def kernel_config_filepath(self):
        return os.path.join(self._bootDir, self.kernel_config_filename)

    @property
    def kernel_config_rules_filename(self):
        return "config-" + self._kernelInfo.postfix + ".rules"

    @property
    def kernel_config_rules_filepath(self):
        return os.path.join(self._bootDir, self.kernel_config_rules_filename)

    @property
    def initrd_filename(self):
        return "initramfs-" + self._kernelInfo.postfix

    @property
    def initrd_filepath(self):
        return os.path.join(self._bootDir, self.initrd_filename)

    @property
    def initrd_tar_filename(self):
        return "initramfs-files-" + self._kernelInfo.postfix + ".tar.bz2"

    @property
    def initrd_tar_filepath(self):
        return os.path.join(self._bootDir, self.initrd_tar_filename)

    def has_kernel_files(self):
        if not os.path.exists(self.kernel_filepath):
            return False
        if not os.path.exists(self.kernel_config_filepath):
            return False
        if not os.path.exists(self.kernel_config_rules_filepath):
            return False
        return True

    def has_initrd_files(self):
        if not os.path.exists(self.initrd_filepath):
            return False
        if not os.path.exists(self.initrd_tar_filepath):
            return False
        return True

    def ___eq___(self, other):
        return self._bbki == other._bbki and self._kernelInfo == other._kernelInfo and self._bootDir == other._bootDir
