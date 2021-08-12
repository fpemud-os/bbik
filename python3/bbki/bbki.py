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


import subprocess
from .util import Util
from .config import BuildInfo, Config
from .repo import Repo
from .repo import BbkiFileExecutor
from .fslayout import FsLayout
from .kernel import KernelInfo
from .kernel import KernelInstaller
from .initramfs import InitramfsInstaller
from .boot import BootEntry
from .boot import Bootloader
from .boot import BootloaderInstaller


class Bbki:

    KERNEL_TYPE_LINUX = "linux"

    ATOM_TYPE_KERNEL = 1
    ATOM_TYPE_KERNEL_ADDON = 2

    BOOT_MODE_EFI = 1
    BOOT_MODE_BIOS = 2

    def __init__(self, cfgdir=None, build_info=None):
        if cfgdir is None:
            cfgdir = "/etc/bbki"

        if build_info is None:
            build_info = BuildInfo()
        if build_info.arch == "native":
            build_info.arch = os.uname().machine
        if build_info.boot_mode == 

            build_info.boot_mode = 



        self.prefix = None



        self._cfg = Config(cfgdir)
        self._fsLayout = FsLayout()
        self._bootLoader = Bootloader()
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

    def get_system_stable_flag(self):
        return self._bootLoader.get_stable_flag()

    def set_system_stable_flag(self, stable):
        return self._bootLoader.set_stable_flag(stable)

    def get_current_boot_entry(self):
        un = os.uname()
        kernelInfo = KernelInfo(un.machine, un.release)
        for bHistoryEntry in [False, True]:
            ret = BootEntry(self._bbki, kernelInfo, history_entry=bHistoryEntry)
            if ret.has_kernel_files() and ret.has_initrd_files():
                return ret
        return None

    def get_pending_boot_entry(self):
        kernelInfo = self._bootLoader.get_current_kernel_info()
        if kernelInfo is None:
            ret = BootEntry(kernelInfo)
            if ret.has_kernel_files() and ret.has_initrd_files():
                return ret
            else:
                return None
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
        assert kernel_atom is not None and kernel_atom.item_type == self.ATOM_TYPE_KERNEL
        assert kernel_addon_atom_list is not None and all([x.item_type == self.ATOM_TYPE_KERNEL_ADDON for x in kernel_addon_atom_list])

        return KernelInstaller(self, kernel_atom, kernel_addon_atom_list)

    def install_initramfs(self, boot_entry):
        obj = InitramfsInstaller(KernelInfo(kernel_atom.verstr), boot_entry)
        obj.install()

    def install_bootloader(self):
        pass

    def update_bootloader_config(self):
        pass

    def check(self, autofix=False):
        assert False

    def remove(self):
        assert False

    def clean_boot_dir(self, pretend=False):
        assert False

    def clean_cache_dir(self, pretend=False):
        DistfilesCache


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