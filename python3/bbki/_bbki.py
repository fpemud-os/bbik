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

from ._po import BootMode
from ._po import KernelType
from ._po import RescueOsSpec
from ._repo import Repo
from ._boot_dir import BootEntry
from ._kernel import KernelInstaller
from ._initramfs import InitramfsInstaller
from ._exception import RunningEnvironmentError

from ._util import Util
from ._po import FsLayout
from ._repo import BbkiFileExecutor
from ._boot_dir import BootDirWriter
from ._kernel import BootEntryUtils
from ._kernel import BootEntryWrapper
from ._bootloader import BootLoader


class Bbki:

    def __init__(self, cfg=None, self_boot=True):
        self._cfg = cfg
        self._bSelfBoot = self_boot

        if self._cfg.get_kernel_type() == KernelType.LINUX:
            self._fsLayout = FsLayout(self)
        else:
            assert False

        self._repoList = [
            Repo(self, self._cfg.data_repo_dir),
        ]

        self._bootDirWriter = BootDirWriter(self)
        self._bootloader = BootLoader(self)

    @property
    def config(self):
        return self._cfg

    @property
    def repositories(self):
        return self._repoList

    @property
    def boot_dir_writer(self):
        return self._bootDirWriter

    @property
    def rescue_os_spec(self):
        return RescueOsSpec(self)

    def check_running_environment(self):
        if not os.path.isdir(self._fsLayout.get_boot_dir()):
            raise RunningEnvironmentError("directory \"%s\" does not exist" % (self._fsLayout.get_boot_dir()))
        if not os.path.isdir(self._fsLayout.get_lib_dir()):
            raise RunningEnvironmentError("directory \"%s\" does not exist" % (self._fsLayout.get_lib_dir()))

        if not Util.cmdCallTestSuccess("make", "-v"):
            raise RunningEnvironmentError("executable \"make\" does not exist")
        if not Util.cmdCallTestSuccess("grubenv", "-V"):
            raise RunningEnvironmentError("executable \"grubenv\" does not exist")
        if not Util.cmdCallTestSuccess("grub-install", "-V"):
            raise RunningEnvironmentError("executable \"grub-install\" does not exist")

    def is_stable(self):
        return self._bootloader.getStatus() == BootLoader.STATUS_NORMAL and self._bootloader.getStableFlag()

    def set_stable(self, value):
        # we use grub environment variable to store stable status
        if self._bootloader.getStatus() != BootLoader.STATUS_NORMAL:
            raise RunningEnvironmentError("bootloader is not properly installed")
        with self._bootDirWriter:
            self._bootloader.setStableFlag(value)

    def get_current_boot_dir(self):
        assert self._bSelfBoot

        for bHistoryEntry in [False, True]:
            ret = BootEntry.new_from_verstr(self, "native", os.uname().release, history_entry=bHistoryEntry)
            if ret.has_kernel_files() and ret.has_initrd_files():
                return ret
        raise RunningEnvironmentError("current boot entry is lost")

    def get_pending_boot_dir(self):
        if self._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
            ret = self._bootloader.getMainBootEntry()
            if not ret.has_kernel_files() or not ret.has_initrd_files():
                raise RunningEnvironmentError("invalid pending boot entry")
            return ret
        else:
            if not self._bSelfBoot:
                tlist = BootEntryUtils.getBootEntryList()
                if len(tlist) > 0:
                    if len(tlist) > 1:
                        raise RunningEnvironmentError("multiple pending boot entries")
                    return tlist[-1]
                else:
                    return None
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

    def install_initramfs(self, host_storage):
        assert host_storage is not None
        assert host_storage.get_root_mount_point() is not None

        with self._bootDirWriter:
            InitramfsInstaller(self, host_storage, self.get_pending_boot_dir()).install()

    def install_bootloader(self, boot_mode, host_storage, aux_os_list, aux_kernel_init_cmdline):
        with self._bootDirWriter:
            if self._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
                pass
            elif self._bootloader.getStatus() == BootLoader.STATUS_NOT_INSTALLED:
                pass
            elif self._bootloader.getStatus() == BootLoader.STATUS_INVALID:
                self._bootloader.remove()
            else:
                assert False

            if boot_mode == BootMode.EFI:
                rootfsMp = host_storage.get_root_mount_point()
                espMp = host_storage.get_esp_mount_point()
                self._bootloader.install(boot_mode, rootfsMp.dev_path, rootfsMp.dev_uuid, espMp.dev_path, espMp.dev_uuid,
                                         None, None,
                                         aux_os_list, aux_kernel_init_cmdline)
            elif boot_mode == BootMode.BIOS:
                rootfsMp = host_storage.get_root_mount_point()
                self._bootloader.install(boot_mode, rootfsMp.dev_path, rootfsMp.dev_uuid, None, None,
                                         host_storage.boot_disk_path, host_storage.boot_disk_id,
                                         aux_os_list, aux_kernel_init_cmdline)
            else:
                assert False

    def clean_boot_dir(self, pretend=False):
        currentBe = self.get_current_boot_dir() if self._bSelfBoot else None
        pendingBe = self.get_pending_boot_dir()

        # get to-be-deleted files in /boot
        bootFileList = None
        if True:
            tset = set(glob.glob(os.path.join(self._fsLayout.get_boot_dir(), "*")))                       # mark /boot/* (no recursion) as to-be-deleted
            if self._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
                tset -= set(self._bootloader.getFilePathList())                                           # don't delete boot-loader files
            tset.discard(self._fsLayout.get_boot_rescue_os_dir())                                         # don't delete /boot/rescue
            if currentBe is not None:
                if currentBe.is_historical():
                    tset.discard(self._fsLayout.get_boot_history_dir())                                   # don't delete /boot/history since some files in it are referenced
                    tset |= set(glob.glob(os.path.join(self._fsLayout.get_boot_history_dir(), "*")))      # mark /boot/history/* (no recursion) as to-be-deleted
                    tset -= set(BootEntryUtils(self._bbki).getBootEntryFilePathList(currentBe))           # don't delete files of current-boot-entry
                else:
                    assert currentBe == pendingBe
            if pendingBe is not None:
                tset -= set(BootEntryUtils(self._bbki).getBootEntryFilePathList(pendingBe))               # don't delete files of pending-boot-entry
            bootFileList = sorted(list(tset))

        # get to-be-deleted files in /lib/modules
        modulesFileList = []
        if os.path.exists(self._fsLayout.get_kernel_modules_dir()):
            tset = set(glob.glob(os.path.join(self._fsLayout.get_kernel_modules_dir(), "*")))              # mark /lib/modules/* (no recursion) as to-be-deleted
            if currentBe is not None:
                tset.discard(currentBe.kernel_modules_dirpath)                                             # don't delete files of current-boot-entry
            if pendingBe is not None and pendingBe != currentBe:
                tset.discard(pendingBe.kernel_modules_dirpath)                                             # don't delete files of pending-boot-entry
            if len(tset) == 0:
                tset.add(self._fsLayout.get_kernel_modules_dir())                                          # delete /lib/modules since it is empty
            modulesFileList = sorted(list(tset))

        # get to-be-deleted files in /lib/firmware
        firmwareFileList = []                                                                              # FIXME
        if os.path.exists(self._fsLayout.get_firmware_dir()):
            tset = set(glob.glob(os.path.join(self._fsLayout.get_firmware_dir(), "**"), recursive=True))   # mark /lib/firmware/* (recursive) as to-be-deleted
            if currentBe is not None:
                tset -= set(BootEntryWrapper(currentBe).get_firmware_filepaths())                          # don't delete files of current-boot-entry
            if pendingBe is not None and pendingBe != currentBe:
                tset -= set(BootEntryWrapper(pendingBe).get_firmware_filepaths())                          # don't delete files of pending-boot-entry
            if len(tset) == 0:
                tset.add(self._fsLayout.get_firmware_dir())                                                # delete /lib/firmware since it is empty
            firmwareFileList = sorted(list(tset))

        # delete files
        if not pretend:
            with self._bootDirWriter:
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

    def remove_bootloader_and_initramfs(self):
        be = self.get_pending_boot_dir()
        with self._bootDirWriter:
            self._bootloader.remove()
            robust_layer.simple_fops.rm(be.initrd_filepath)
            robust_layer.simple_fops.rm(be.initrd_tar_filepath)

    def remove_all(self):
        with self._bootDirWriter:
            self._bootloader.remove()                                                 # remove MBR if necessary
            Util.removeDirContent(self._fsLayout.get_boot_dir())                      # remove /boot/*
        robust_layer.simple_fops.rm(self._fsLayout.get_firmware_dir())                # remove /lib/firmware
        robust_layer.simple_fops.rm(self._fsLayout.get_kernel_modules_dir())          # remove /lib/modules

    def check(self, autofix=False):
        assert False
