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
import glob
import robust_layer.simple_fops
from ._boot_dir import BootEntryUtils
from ._boot_dir import BootEntryWrapper
from ._bootloader import BootLoader


class Checker:

    def __init__(self, bbki, auto_fix=False, error_callback=None):
        self._bbki = bbki
        self._bAutoFix = auto_fix
        self._errCb = error_callback if error_callback is not None else self._doNothing

    def checkBootDir(self):
        if self._bbki._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
            pass
        elif self._bbki._bootloader.getStatus() == BootLoader.STATUS_NOT_INSTALLED:
            self._errCb("Boot-loader is not installed.")
        elif self._bbki._bootloader.getStatus() == BootLoader.STATUS_INVALID:
            self._errCb("Boot-loader is invalid.")
        else:
            assert False

        pendingBe = self._bbki.get_pending_boot_entry()
        if pendingBe is None:
            self._errCb("No pending boot entry.")
        else:
            assert pendingBe.has_kernel_files()
            if pendingBe.has_initrd_files():
                self._errCb("Pending boot entry has no initramfs files.")

        if self._bbki.get_current_boot_entry() != pendingBe:
            self._errCb("Current boot entry and pending boot entry are different, reboot needed.")

    def checkKernelModulesDir(self):
        obj = BootEntryUtils(self._bbki)
        beList = obj.getBootEntryList() + obj.getBootEntryList(history_entry=True)

        # check missing directories in /lib/modules
        for be in beList:
            bew = BootEntryWrapper(be)
            if not os.path.exists(bew.modules_dir):
                self._errCb("Kernel module directory \"%s\" does not exist." % (bew.modules_dir))

        # check redundant directories in /lib/modules
        kmodFileList = obj.getRedundantKernelModulesDirs(beList)
        if len(kmodFileList) > 0:
            if self._bAutoFix:
                for fullfn in kmodFileList:
                    robust_layer.simple_fops.rm(fullfn)
                if len(os.listdir(self._bbki._fsLayout.get_kernel_modules_dir())) == 0:
                    robust_layer.simple_fops.rm(self._bbki._fsLayout.get_kernel_modules_dir())
            else:
                for fullfn in kmodFileList:
                    self._errCb("Redundant kernel module directory \"%s\"." % (fullfn))

    def checkFirmwareDir(self):
        obj = BootEntryUtils(self._bbki)
        beList = obj.getBootEntryList() + obj.getBootEntryList(history_entry=True)

        # check missing files in /lib/firmware
        processedList = set()
        for be in beList:
            for fullfn in BootEntryWrapper(be).get_firmware_filepaths():
                if fullfn in processedList:
                    continue
                if not os.path.exists(fullfn):
                    self._errCb("Firmware file \"%s\" does not exist." % (fullfn))
                processedList.add(fullfn)

        # check redundant files in /lib/firmware
        firmwareFileList = BootEntryUtils(self).getRedundantFirmwareFiles(beList)
        if len(firmwareFileList) > 0:
            if self._bAutoFix:
                for fullfn in firmwareFileList:
                    robust_layer.simple_fops.rm(fullfn)
                # FIXME: need to delete intermediate empty directories
                if len(os.listdir(self._bbki._fsLayout.get_firmware_dir())) == 0:
                    robust_layer.simple_fops.rm(self._bbki._fsLayout.get_firmware_dir())
            else:
                for fullfn in firmwareFileList:
                    self._errCb("Redundant firmware file \"%s\"." % (fullfn))

    def _doNothing(self, msg):
        pass
