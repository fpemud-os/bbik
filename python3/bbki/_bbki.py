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
import platform
import robust_layer.simple_fops

from ._config import ConfigBase
from .etcdir_cfg import Config as EtcDirConfig

from ._po import BootMode
from ._po import KernelType
from ._po import RescueOsSpec
from ._po import HostMountPoint
from ._repo import Repo
from ._boot_entry import BootEntry
from ._kernel import KernelInstaller
from ._exception import RunningEnvironmentError

from ._util import Util
from ._util import PhysicalDiskMounts
from ._po import FsLayout
from ._repo import BbkiAtomExecutor
from ._boot_entry import BootEntryUtils
from ._boot_entry import BootEntryWrapper
from ._bootloader import BootLoader
from ._check import Checker


class Bbki:

    def __init__(self, cfg=None, self_boot=True):
        if cfg is not None:
            assert isinstance(cfg, ConfigBase)
        else:
            cfg = EtcDirConfig()
        assert isinstance(self_boot, bool)

        self._cfg = cfg
        self._bSelfBoot = self_boot

        if self._cfg.get_kernel_type() == KernelType.LINUX:
            self._fsLayout = FsLayout(self)
        else:
            assert False

        self._repoList = [
            Repo(self, self._cfg.data_repo_dir),
        ]

        # FIXME: we should not create boot-loader object here, we should support no boot-loader senario
        rootfsMnt = PhysicalDiskMounts.find_root_entry()
        bootMnt = PhysicalDiskMounts.find_entry_by_mount_point(self._fsLayout.get_boot_dir())
        self._bootloader = BootLoader(self, rootfsMnt, bootMnt)

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

        if not Util.cmdCallTestSuccess("make", "-v"):
            raise RunningEnvironmentError("executable \"make\" does not exist")

        if not Util.cmdCallTestSuccess("grub-script-check", "-V"):
            raise RunningEnvironmentError("executable \"grub-script-check\" does not exist")
        if not Util.cmdCallTestSuccess("grub-editenv", "-V"):
            raise RunningEnvironmentError("executable \"grub-editenv\" does not exist")

    def get_current_boot_entry(self):
        assert self._bSelfBoot

        for bHistoryEntry in [False, True]:
            ret = BootEntry(self, platform.machine(), platform.release(), history_entry=bHistoryEntry)
            if ret.has_kernel_files() and ret.has_initrd_files():
                return ret
        raise RunningEnvironmentError("current boot entry is lost")

    def get_pending_boot_entry(self):
        if self._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
            mbe = self._bootloader.getMainBootEntry()
            if mbe.has_kernel_files() and mbe.has_initrd_files():
                return mbe
        return None

    def get_boot_entries(self):
        ret = []
        for kernelFile in sorted(os.listdir(self._fsLayout.get_boot_dir()), reverse=True):
            if kernelFile.startswith("kernel-"):
                ret.append(BootEntryUtils(self).new_from_postfix(kernelFile[len("kernel-"):]))
        return ret

    def get_history_boot_entries(self):
        if not os.path.exists(self._fsLayout.get_boot_history_dir()):
            return []

        ret = []
        for kernelFile in sorted(os.listdir(self._fsLayout.get_boot_history_dir()), reverse=True):
            if kernelFile.startswith("kernel-"):
                be = BootEntryUtils(self).new_from_postfix(kernelFile[len("kernel-"):], history_entry=True)
                if be.has_kernel_files() and be.has_initrd_files():
                    ret.append(be)
        return ret

    def get_kernel_atom(self):
        items = self._repoList[0].get_atoms_by_type_name(self._cfg.get_kernel_type(), Repo.ATOM_TYPE_KERNEL, self._cfg.get_kernel_name())
        items = [x for x in items if self._cfg.test_version_mask(x.fullname, x.verstr)]                    # filter by bbki-config
        if len(items) > 0:
            return items[-1]
        else:
            return None

    def get_kernel_addon_atoms(self):
        ret = []
        for name in self._cfg.get_kernel_addon_names():
            items = self._repoList[0].get_atoms_by_type_name(self._cfg.get_kernel_type(), Repo.ATOM_TYPE_KERNEL_ADDON, name)
            items = [x for x in items if self._cfg.test_version_mask(x.fullname, x.verstr)]                # filter by bbki-config
            if len(items) > 0:
                ret.append(items[-1])
        return ret

    def get_initramfs_atom(self):
        items = self._repoList[0].get_atoms_by_type_name(self._cfg.get_kernel_type(), Repo.ATOM_TYPE_INITRAMFS, self._cfg.get_initramfs_name())
        items = [x for x in items if self._cfg.test_version_mask(x.fullname, x.verstr)]                    # filter by bbki-config
        if len(items) > 0:
            return items[-1]
        else:
            return None

    def fetch(self, atom):
        BbkiAtomExecutor(atom).exec_fetch()

    def get_kernel_installer(self, kernel_atom, kernel_addon_atom_list, initramfs_atom=None):
        assert kernel_atom.atom_type == Repo.ATOM_TYPE_KERNEL
        assert all([x.atom_type == Repo.ATOM_TYPE_KERNEL_ADDON for x in kernel_addon_atom_list])

        return KernelInstaller(self, kernel_atom, kernel_addon_atom_list, initramfs_atom)

    def install_initramfs(self, initramfs_atom, mount_points, boot_entry):
        assert mount_points[0].mountpoint == "/"
        assert Util.checkListUnique(mount_points, key=lambda x: x.mountpoint)
        assert boot_entry.has_kernel_files() and not boot_entry.is_historical()

        obj = BbkiAtomExecutor(initramfs_atom)
        obj.create_tmpdirs()
        try:
            obj.exec_src_unpack()
            obj.exec_initramfs_install(mount_points, boot_entry)
        finally:
            obj.remove_tmpdirs()

    def install_bootloader(self, boot_mode, mount_points, main_boot_entry, aux_os_list, aux_kernel_init_cmdline):
        assert mount_points[0].mountpoint == "/"
        assert Util.checkListUnique(mount_points, key=lambda x: x.mountpoint)
        assert all([x.device is not None for x in mount_points])

        def __cmpHostMountPointAndPhysicalDiskMountsEntry(obj1, obj2):
            assert isinstance(obj1, HostMountPoint) and isinstance(obj2, PhysicalDiskMounts.Entry)
            return obj1.device == obj2.device and obj1.mountpoint == obj2.mountpoint and obj1.fstype == obj2.fstype and obj1.opts == obj2.opts

        assert __cmpHostMountPointAndPhysicalDiskMountsEntry(mount_points[0], self._bootloader.getRootfsMnt())
        if boot_mode == BootMode.EFI:
            assert __cmpHostMountPointAndPhysicalDiskMountsEntry(Util.findInList(mount_points, key=lambda x: x.mountpoint == "/boot"), self._bootloader.getBootMnt())
        elif boot_mode == BootMode.BIOS:
            pass
        else:
            assert False

        self._bootloader.install(boot_mode, main_boot_entry, aux_os_list, aux_kernel_init_cmdline)

    def update_bootloader(self, main_boot_entry=None, aux_os_list=None, aux_kernel_init_cmdline=None):
        assert self._bootloader.getStatus() == BootLoader.STATUS_NORMAL

        self._bootloader.update(main_boot_entry, aux_os_list, aux_kernel_init_cmdline)

    def get_stable_flag(self):
        return self._bootloader.getStatus() == BootLoader.STATUS_NORMAL and self._bootloader.getStableFlag()

    def set_stable_flag(self, value):
        # we use grub environment variable to store stable status
        if self._bootloader.getStatus() != BootLoader.STATUS_NORMAL:
            raise RunningEnvironmentError("bootloader is not properly installed")
        self._bootloader.setStableFlag(value)

    def clean_boot_entry_files(self, pretend=False):
        if self._bSelfBoot:
            currentBe = self.get_current_boot_entry()
            beList = self.get_boot_entries()
            fullBeList = beList if not currentBe.is_historical() else beList + [currentBe]
        else:
            currentBe = None
            beList = self.get_boot_entries()
            fullBeList = beList

        # get to-be-deleted files in /boot
        bootFileList = None
        if True:
            tset = set(glob.glob(os.path.join(self._fsLayout.get_boot_dir(), "*")))                     # mark /boot/* (no recursion) as to-be-deleted
            if self._bootloader.getStatus() == BootLoader.STATUS_NORMAL:
                tset -= set(self._bootloader.getFilepaths())                                           # don't delete boot-loader files
            tset.discard(self._fsLayout.get_boot_rescue_os_dir())                                       # don't delete /boot/rescue
            if currentBe is not None:
                if currentBe.is_historical():
                    tset.discard(self._fsLayout.get_boot_history_dir())                                 # don't delete /boot/history since some files in it are referenced
                    tset |= set(glob.glob(os.path.join(self._fsLayout.get_boot_history_dir(), "*")))    # mark /boot/history/* (no recursion) as to-be-deleted
                    tset -= set(BootEntryWrapper(currentBe).get_filepaths())                            # don't delete files of current-boot-entry
            for be in beList:
                tset -= set(BootEntryWrapper(be).get_filepaths())                                       # don't delete files of pending-boot-entry
            bootFileList = sorted(list(tset))

        # get to-be-deleted files in /lib/modules
        modulesFileList = BootEntryUtils(self).getRedundantKernelModulesDirs(fullBeList)
        if modulesFileList == os.listdir(self._fsLayout.get_kernel_modules_dir()):
            modulesFileList.append(self._fsLayout.get_kernel_modules_dir())

        # get to-be-deleted files in /lib/firmware
        firmwareFileList = BootEntryUtils(self).getRedundantFirmwareFiles(fullBeList)

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
        #             items = repo.get_atoms_by_type_name(atomType, atomName)
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
        self._bootloader.remove(bForce=True)                                      # remove MBR if necessary
        robust_layer.simple_fops.truncate_dir(self._fsLayout.get_boot_dir())      # remove /boot/*
        robust_layer.simple_fops.rm(self._fsLayout.get_firmware_dir())            # remove /lib/firmware
        robust_layer.simple_fops.rm(self._fsLayout.get_kernel_modules_dir())      # remove /lib/modules

    def check_config(self, autofix=False, error_callback=None):
        self._cfg.do_check(self, autofix, error_callback)

    def check_repositories(self, autofix=False, error_callback=None):
        obj = Checker(self, autofix, error_callback)
        obj.checkRepositories()

    def check_boot_entry_files(self, autofix=False, error_callback=None):
        obj = Checker(self, autofix, error_callback)
        obj.checkBootDir()
        obj.checkKernelModulesDir()
        obj.checkFirmwareDir()
