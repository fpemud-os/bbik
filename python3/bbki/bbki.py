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
from .util import Util
from .host_info import HostInfoUtil
from .fs_layout import FsLayoutLinux
from .config import Config
from .repo import Repo
from .repo import BbkiFileExecutor
from .kernel import KernelInfo
from .kernel import KernelInstaller
from .initramfs import InitramfsInstaller
from .boot import BootEntry
from .boot import Bootloader
from .boot import BootloaderInstaller


class Bbki:

    KERNEL_TYPE_LINUX = "linux"

    BOOT_MODE_EFI = "efi"
    BOOT_MODE_BIOS = "bios"

    ATOM_TYPE_KERNEL = 1
    ATOM_TYPE_KERNEL_ADDON = 2

    def __init__(self, target_host_info, target_host_is_myself=True, cfgdir=None):
        self._targetHostInfo = target_host_info
        self._bForSelf = target_host_is_myself

        if cfgdir is None:
            cfgdir = "/etc/bbki"
        self._cfg = Config(cfgdir)

        if self._cfg.get_kernel_type() == self.KERNEL_TYPE_LINUX:
            self._fsLayout = FsLayoutLinux(self)
        else:
            assert False

        self._repoList = [
            Repo(self._cfg.data_repo_dir),
        ]

    @property
    def config(self):
        return self._cfg

    @property
    def repositories(self):
        return self._repoList

    def check_running_environment(self):
        if not Util.cmdCallTestSuccess("sed", "--version"):
            raise RunningEnvironmentError("executable \"sed\" does not exist")
        if not Util.cmdCallTestSuccess("make", "-V"):
            raise RunningEnvironmentError("executable \"make\" does not exist")
        if not Util.cmdCallTestSuccess("grub-editenv", "-V"):
            raise RunningEnvironmentError("executable \"grub-editenv\" does not exist")

    def get_current_boot_entry(self):
        if not self._bForSelf:
            return None

        un = os.uname()
        kernelInfo = KernelInfo(un.machine, un.release)
        for bHistoryEntry in [False, True]:
            ret = BootEntry(self._bbki, kernelInfo, history_entry=bHistoryEntry)
            if ret.has_kernel_files() and ret.has_initrd_files():
                return ret
        return None

    def get_pending_boot_entry(self, strict=True):
        ret = Bootloader(self).getCurrentBootEntry()
        if ret is not None and (not strict or (ret.has_kernel_files() and ret.has_initrd_files())):
            return ret
        else:
            return None

    def get_kernel_atom(self):
        items = self._repoList[0].get_items_by_type_name(self.ATOM_TYPE_KERNEL, self._cfg.get_kernel_type())
        items = [x for x in items if self._cfg.check_version_mask(x.fullname, x.verstr)]                    # filter by bbki-config
        if len(items) > 0:
            return items[-1]
        else:
            return None

    def get_kernel_addon_atoms(self):
        ret = []
        for name in self._cfg.get_kernel_addon_names():
            items = self._repoList[0].get_items_by_type_name(self.ATOM_TYPE_KERNEL_ADDON, name)
            items = [x for x in items if self._cfg.check_version_mask(x.fullname, x.verstr)]                # filter by bbki-config
            if len(items) > 0:
                ret.append(items[-1])
        return ret

    def fetch(self, atom):
        BbkiFileExecutor(atom).exec_fetch()

    def get_kernel_installer(self, kernel_atom, kernel_addon_atom_list):
        assert kernel_atom.item_type == self.ATOM_TYPE_KERNEL
        assert all([x.item_type == self.ATOM_TYPE_KERNEL_ADDON for x in kernel_addon_atom_list])

        return KernelInstaller(self, kernel_atom, kernel_addon_atom_list)

    def install_initramfs(self, boot_entry):
        assert boot_entry.has_kernel_files()

        if self._targetHostInfo.boot_disk is None:
            raise RunningEnvironmentError("no boot/root device specified")

        obj = InitramfsInstaller(boot_entry)
        obj.install()

    def install_bootloader(self):
        if self._targetHostInfo.boot_disk is None:
            raise RunningEnvironmentError("no boot/root device specified")

        pass

    def reinstall_bootloader(self):
        if self._targetHostInfo.boot_disk is None:
            raise RunningEnvironmentError("no boot/root device specified")

        pass

    def update_bootloader(self):
        if self._targetHostInfo.boot_disk is None:
            raise RunningEnvironmentError("no boot/root device specified")

        pass

    def get_kernel(self, kernel_verstr):
        return Kernel(kernel_verstr)


    def check(self, autofix=False):
        assert False

    def clean_boot_dir(self, pretend=False):
        assert False

    def clean_cache_dir(self, pretend=False):
        assert False

    def remove(self):
        assert False


class RunningEnvironmentError(Exception):
    pass


class ConfigError(Exception):
    pass


class RepoError(Exception):
    pass


class FetchError(Exception):
    pass


class KernelInstallError(Exception):
    pass


class InitramfsInstallError(Exception):
    pass


class BootloaderInstallError(Exception):
    pass