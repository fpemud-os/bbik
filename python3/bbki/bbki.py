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


from .config import Config
from .repo import Repo
from .repo import BbkiFileExecutor
from .fslayout import BootEntry
from .fslayout import FsLayout
from .kernel import KernelBuildTarget
from .kernel import KernelInstaller
from .initramfs import InitramfsInstaller


class Bbki:

    KERNEL_TYPE_LINUX = "linux"

    ITEM_TYPE_KERNEL = 1
    ITEM_TYPE_KERNEL_ADDON = 2

    def __init__(self, cfgdir=None):
        self._cfg = Config(cfgdir)
        self._fsLayout = FsLayout()
        self._repoList = [
            Repo(self._cfg.data_repo_dir),
        ]

    @property
    def config(self):
        return self._cfg

    @property
    def repositories(self):
        return self._repoList

    def get_current_boot_entry(self):
        self._fsLayout.find_current_boot_entry()

    def get_pending_boot_entry(self):
        item = self.get_kernel()
        buildTarget = KernelBuildTarget.new_from_verstr("amd64", item.verstr())
        return BootEntry(buildTarget)

    def get_kernel(self):
        items = self._repoList[0].get_items_by_type_name(self.ITEM_TYPE_KERNEL, self._cfg.get_kernel_type())
        items = [x for x in items if self._cfg.check_version_mask(x.fullname, x.verstr)]                    # filter by bbki-config
        if len(items) > 0:
            return items[-1]
        else:
            return None

    def get_kernel_addons(self):
        ret = []
        for name in self._cfg.get_kernel_addon_names():
            items = self._repoList[0].get_items_by_type_name(self.ITEM_TYPE_KERNEL_ADDON, name)
            items = [x for x in items if self._cfg.check_version_mask(x.fullname, x.verstr)]                # filter by bbki-config
            if len(items) > 0:
                ret.append(items[-1])
        return ret

    def fetch(self, bbki_item):
        BbkiFileExecutor(bbki_item).exec_fetch()

    def get_kernel_installer(self):
        return KernelInstaller(self)

    def get_initramfs_installer(self, boot_entry):
        return InitramfsInstaller(boot_entry)

    def get_bootloader_installer(self):
        assert False

    def check(self, autofix=False):
        assert False

    def clean_boot_dir(self, pretend=False):
        assert False

    def clean_cache_dir(self, pretend=False):
        DistfilesCache


        assert False


class BbkiConfigError(Exception):
    pass


class BbkiRepoError(Exception):
    pass


class BbkiFetchError(Exception):
    pass


class BbkiKernelInstallError(Exception):
    pass


class BbkiInitramfsInstallError(Exception):
    pass


class BbkiBootloaderInstallError(Exception):
    pass