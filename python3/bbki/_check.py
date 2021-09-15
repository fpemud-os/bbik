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
import robust_layer.simple_fops
from ._util import Util
from ._boot_entry import BootEntryUtils
from ._boot_entry import BootEntryWrapper
from ._bootloader import BootLoader


class Checker:

    def __init__(self, bbki, auto_fix=False, error_callback=None):
        self._bbki = bbki
        self._bAutoFix = auto_fix
        self._errCb = error_callback if error_callback is not None else self._doNothing

    def checkBootDir(self):
        # check bootloader
        if self._bbki._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
            pass
        elif self._bbki._bootloader.getStatus() == BootLoader.STATUS_NOT_INSTALLED:
            self._errCb("Boot-loader is not installed.")
        elif self._bbki._bootloader.getStatus() == BootLoader.STATUS_INVALID:
            self._errCb("Boot-loader is invalid.")
        else:
            assert False

        # check pending boot entry
        pendingBe = self._bbki.get_pending_boot_entry()
        if pendingBe is None:
            self._errCb("No pending boot entry, system is not bootable.")

        # check current boot entry
        if self._bbki._bSelfBoot:
            if self._bbki.get_current_boot_entry() != pendingBe:
                self._errCb("Current boot entry and pending boot entry are different, reboot needed.")

        # check boot entries
        beList = self._bbki.get_boot_entries()
        if len(beList) > 1:
            if self._bAutoFix and pendingBe is not None:
                for be in beList:
                    if be != pendingBe:
                        be.move_to_history()
                self._bbki.update_bootloader()
                beList = [pendingBe]
            else:
                self._errCb("Multiple boot entries found.")
        for be in beList:
            if not be.has_initrd_files():
                self._errCb("Boot entry \"%s\" has no initramfs files." % (be.kernel_filename))

        # check redundant files in /boot
        if self._bbki._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
            bootloaderFileList = self._bbki._bootloader.get_filepaths()
        elif self._bbki._bootloader.getStatus() == BootLoader.STATUS_NOT_INSTALLED:
            bootloaderFileList = []
        else:
            bootloaderFileList = None
        if bootloaderFileList is not None:
            tset = set(Util.globDirRecursively(self._bbki._fsLayout.get_boot_dir()))
            tset -= set(bootloaderFileList)
            for be in beList:
                tset -= set(BootEntryWrapper(be).get_filepaths())
            if True:
                tlist = self._bbki.get_history_boot_entries()
                if len(tlist) > 0:
                    for t in tlist:
                        tset -= set(BootEntryWrapper(t).get_filepaths())
                    tset.discard(self._bbki._fsLayout.get_boot_history_dir())
            tset.discard(self._bbki._fsLayout.get_boot_rescue_os_dir())
            if len(tset) > 0:
                if self._bAutoFix:
                    for fullfn in tset:
                        robust_layer.simple_fops.rm(fullfn)
                else:
                    for fullfn in sorted(list(tset)):
                        self._errCb("Redundant file \"%s\"." % (fullfn))

        # check /boot/grub/grub.cfg
        pass

        # check free space
        pass

    def checkKernelModulesDir(self):
        beList = self._bbki.get_boot_entries() + self._bbki.get_history_boot_entries()

        # check missing directories in /lib/modules
        for be in beList:
            if not os.path.exists(be.kernel_modules_dirpath):
                self._errCb("Missing kernel module directory \"%s\"." % (be.kernel_modules_dirpath))

        # check redundant directories in /lib/modules
        kmodFileList = BootEntryUtils(self._bbki).getRedundantKernelModulesDirs(beList)
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
        beList = self._bbki.get_boot_entries() + self._bbki.get_history_boot_entries()

        # check missing files in /lib/firmware
        processedList = set()
        for be in beList:
            for fullfn in BootEntryWrapper(be).get_firmware_filepaths():
                if fullfn in processedList:
                    continue
                if not os.path.exists(fullfn):
                    self._errCb("Missing firmware file \"%s\"." % (fullfn))
                processedList.add(fullfn)

        # check redundant files in /lib/firmware
        firmwareFileList = BootEntryUtils(self._bbki).getRedundantFirmwareFiles(beList)
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
