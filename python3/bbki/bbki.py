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

from .static import KernelType
from .static import BootMode
from .static import RescueOsSpec
from .repo import Repo
from .boot_entry import BootEntry
from .kernel import KernelInstaller
from .exception import RunningEnvironmentError

from .util import Util
from .fs_layout import FsLayout
from .repo import BbkiFileExecutor
from .boot_entry import BootEntryUtils
from .kernel import BootEntryWrapper
from .initramfs import InitramfsInstaller
from .bootloader import BootLoaderGrub


class Bbki:

    def __init__(self, target_host_info, target_host_is_myself=True, cfg=None):
        self._targetHostInfo = target_host_info
        self._bForSelf = target_host_is_myself
        self._cfg = cfg

        if self._cfg.get_kernel_type() == KernelType.LINUX:
            self._fsLayout = FsLayout(self)
        else:
            assert False

        self._repoList = [
            Repo(self, self._cfg.data_repo_dir),
        ]

    @property
    def config(self):
        return self._cfg

    @property
    def repositories(self):
        return self._repoList

    @property
    def rescue_os_spec(self):
        return RescueOsSpec(self)

    def check_running_environment(self):
        if not os.path.isdir(self._fsLayout.get_boot_dir()):
            raise RunningEnvironmentError("directory \"%s\" does not exist" % (self._fsLayout.get_boot_dir()))
        if not os.path.isdir(self._fsLayout.get_lib_dir()):
            raise RunningEnvironmentError("directory \"%s\" does not exist" % (self._fsLayout.get_lib_dir()))

        if not Util.cmdCallTestSuccess("sed", "--version"):
            raise RunningEnvironmentError("executable \"sed\" does not exist")
        if not Util.cmdCallTestSuccess("make", "-v"):
            raise RunningEnvironmentError("executable \"make\" does not exist")
        if not Util.cmdCallTestSuccess("grub-install", "-V"):
            raise RunningEnvironmentError("executable \"grub-install\" does not exist")

    def get_current_boot_entry(self):
        if not self._bForSelf:
            return None

        for bHistoryEntry in [False, True]:
            ret = BootEntry.new_from_verstr(self, "native", os.uname().release, history_entry=bHistoryEntry)
            if ret.has_kernel_files() and ret.has_initrd_files():
                return ret
        return None

    def get_pending_boot_entry(self, strict=True):
        ret = BootLoaderGrub(self).getMainBootEntry()
        if ret is not None and (not strict or (ret.has_kernel_files() and ret.has_initrd_files())):
            return ret
        else:
            return None

    def has_rescue_os(self):
        return os.path.exists(self._fsLayout.get_boot_rescue_os_dir())

    def get_kernel_atom(self):
        items = self._repoList[0].get_items_by_type_name(Repo.ATOM_TYPE_KERNEL, self._cfg.get_kernel_type())
        items = [x for x in items if self._cfg.check_version_mask(x.fullname, x.verstr)]                    # filter by bbki-config
        if len(items) > 0:
            return items[-1]
        else:
            return None

    def get_kernel_addon_atoms(self):
        ret = []
        for name in self._cfg.get_kernel_addon_names():
            items = self._repoList[0].get_items_by_type_name(Repo.ATOM_TYPE_KERNEL_ADDON, name)
            items = [x for x in items if self._cfg.check_version_mask(x.fullname, x.verstr)]                # filter by bbki-config
            if len(items) > 0:
                ret.append(items[-1])
        return ret

    def fetch(self, atom):
        BbkiFileExecutor(atom).exec_fetch()

    def get_kernel_installer(self, kernel_atom, kernel_addon_atom_list):
        assert kernel_atom.atom_type == Repo.ATOM_TYPE_KERNEL
        assert all([x.atom_type == Repo.ATOM_TYPE_KERNEL_ADDON for x in kernel_addon_atom_list])

        return KernelInstaller(self, kernel_atom, kernel_addon_atom_list)

    def install_initramfs(self, boot_entry):
        InitramfsInstaller(self, boot_entry).install()

    def install_bootloader(self):
        BootLoaderGrub(self).install()

    def reinstall_bootloader(self):
        obj = BootLoaderGrub(self)
        obj.remove()
        obj.install()

    def update_bootloader(self):
        BootLoaderGrub(self).update()

    def check(self, autofix=False):
        assert False

    def clean_boot_entries(self, pretend=False):
        if self._targetHostInfo.boot_mode is None and BootLoaderGrub(self).isInstalled():
            raise RunningEnvironmentError("unable to clean when boot-loader installed but boot mode is unspecified")

        currentBe = self.get_current_boot_entry()
        pendingBe = self.get_pending_boot_entry()

        # get to-be-deleted files in /boot
        bootFileList = None
        if True:
            tset = set(glob.glob(os.path.join(self._bbki._fsLayout.get_boot_dir(), "*")))                       # mark /boot/* (no recursion) as to-be-deleted
            if self._targetHostInfo.boot_mode is None:
                pass
            if self._targetHostInfo.boot_mode == BootMode.EFI:
                tset.discard(self._bbki._fsLayout.get_boot_grub_dir())                                          # don't delete /boot/grub
                tset.discard(self._bbki._fsLayout.get_boot_grub_efi_dir())                                      # don't delete /boot/EFI
            elif self._targetHostInfo.boot_mode == BootMode.BIOS:
                tset.discard(self._bbki._fsLayout.get_boot_grub_dir())                                          # don't delete /boot/grub
            else:
                assert False
            tset.discard(self._bbki._fsLayout.get_boot_rescue_os_dir())                                         # don't delete /boot/rescue
            if currentBe is not None:
                if currentBe.is_historical():
                    tset.discard(self._bbki._fsLayout.get_boot_history_dir())                                   # don't delete /boot/history since some files in it are referenced
                    tset |= set(glob.glob(os.path.join(self._bbki._fsLayout.get_boot_history_dir(), "*")))      # mark /boot/history/* (no recursion) as to-be-deleted
                    tset -= set(BootEntryUtils(self._bbki).getBootEntryFilePathList(currentBe))                 # don't delete files of current-boot-entry
                else:
                    assert currentBe == pendingBe
            if pendingBe is not None:
                tset -= set(BootEntryUtils(self._bbki).getBootEntryFilePathList(pendingBe))                     # don't delete files of pending-boot-entry
            bootFileList = sorted(list(tset))

        # get to-be-deleted files in /lib/modules
        modulesFileList = []
        if os.path.exists(self._bbki._fsLayout.get_kernel_modules_dir()):
            tset = set(glob.glob(os.path.join(self._bbki._fsLayout.get_kernel_modules_dir(), "*")))             # mark /lib/modules/* (no recursion) as to-be-deleted
            if currentBe is not None:
                tset.discard(currentBe.kernel_modules_dirpath)                                                  # don't delete files of current-boot-entry
            if pendingBe is not None and pendingBe != currentBe:
                tset.discard(pendingBe.kernel_modules_dirpath)                                                  # don't delete files of pending-boot-entry
            if len(tset) == 0:
                tset.add(self._bbki._fsLayout.get_kernel_modules_dir())                                         # delete /lib/modules since it is empty
            modulesFileList = sorted(list(tset))

        # get to-be-deleted files in /lib/firmware
        firmwareFileList = []                                                                                   # FIXME
        if os.path.exists(self._bbki._fsLayout.get_firmware_dir()):
            tset = set(glob.glob(os.path.join(self._bbki._fsLayout.get_firmware_dir(), "**"), recursive=True))   # mark /lib/firmware/* (recursive) as to-be-deleted
            if currentBe is not None:
                tset -= set(BootEntryWrapper(currentBe).get_firmware_filepaths())                               # don't delete files of current-boot-entry
            if pendingBe is not None and pendingBe != currentBe:
                tset -= set(BootEntryWrapper(pendingBe).get_firmware_filepaths())                               # don't delete files of pending-boot-entry
            if len(tset) == 0:
                tset.add(self._bbki._fsLayout.get_firmware_dir())                                               # delete /lib/firmware since it is empty
            firmwareFileList = sorted(list(tset))

        # delete files
        if not pretend:
            for fullfn in bootFileList:
                robust_layer.simple_fops.rm(fullfn)
            for fullfn in modulesFileList:
                robust_layer.simple_fops.rm(fullfn)
            for fullfn in firmwareFileList:
                robust_layer.simple_fops.rm(fullfn)

        # return value
        return (bootFileList, modulesFileList, firmwareFileList)

    def clean_distfiles(self, pretend=False):
        return []                               # FIXME
        # def findDeprecatedFiles(self, destructive=False):
        #     keepFiles = set()
        #     for repo in self._bbki.repositories:
        #         for atomType, atomName in repo.query_atom_type_name():
        #             items = repo.get_items_by_type_name(atomType, atomName)
        #             if destructive:
        #                 items = [items[-1]]
        #             for item in items:
        #                 keepFiles |= set([fn for t, r, fn in item.get_distfiles()])
        #     keepFiles.add("git-src")

        #     ret = []
        #     for fn in os.listdir(self._bbki.cache_distfiles_dir):
        #         if fn not in keepFiles:
        #             ret.append(fn)
        #             continue
        #         if fn == "git-src":
        #             for fn2 in os.listdir(os.path.join(self._bbki.cache_distfiles_dir, "git-src")):
        #                 fn2 = os.path.join("git-src", fn2)
        #                 if fn2 in keepFiles:
        #                     continue
        #                 ret.append(fn2)
        #             continue
        #     return ret

    def remove_all(self):
        # remove boot-loader (may change harddisk MBR, need valid self._targetHostInfo.boot_mode and self._targetHostInfo.mount_point_list)
        bootloader = BootLoaderGrub(self)
        if bootloader.isInstalled():
            bootloader.remove()

        Util.removeDirContent(self._bbki._fsLayout.get_boot_dir())                      # remove /boot/*
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_firmware_dir())            # remove /lib/firmware
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_kernel_modules_dir())      # remove /lib/modules
