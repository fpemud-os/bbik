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

"""
bbki

@author: Fpemud
@license: GPLv3 License
@contact: fpemud@sina.com
"""

__author__ = "fpemud@sina.com (Fpemud)"
__version__ = "0.0.1"


import os
from .config import Config
from .repo import Repository


class Bbki:

    KERNEL_TYPE_LINUX = "linux"

    ITEM_TYPE_KERNEL = 1
    ITEM_TYPE_KERNEL_ADDON = 2

    def __init__(self, kernel_type, cfgdir=None):
        assert kernel_type in [self.KERNEL_TYPE_LINUX]

        self._kernelType = kernel_type
        self._cfg = Config(cfgdir)
        self._repoList = [
            Repository(self._cfg.data_repo_dir),
        ]

    @property
    def config(self):
        return self._cfg

    @property
    def repositories(self):
        return self._repoList

    def get_kernel(self):
        assert False

    def get_kernel_addons(self):
        assert False

    def get_syncer(self):
        assert False

    def get_kernel_installer(self):
        assert False

    def get_initramfs_installer(self):
        assert False

    def get_bootloader_installer(self):
        assert False

    def check(self, autofix=False):
        assert False

    def clean_boot_dir(self, pretend=False):
        assert False

    def clean_cache_dir(self, pretend=False):
        assert False


class BbkiItem:

    def __init__(self, bbki, item_type, item_name):
        self._bbki = bbki
        self._itemType = item_type
        self._itemName = item_name

    @property
    def kernel_type(self):
        return self._bbki._kernelType

    @property
    def item_type(self):
        return self._itemType

    @property
    def name(self):
        return self._itemName


class BbkiSubItem:

    def __init__(self, item):
        self._item = item
        self._ver = None
        self._revision = None

    @property
    def kernel_type(self):
        return self._item.kernel_tpye

    @property
    def item_type(self):
        return self._item.item_type

    @property
    def name(self):
        return self._item.name

    @property
    def version(self):
        return self._ver

    @property
    def revision(self):
        return self._revision
