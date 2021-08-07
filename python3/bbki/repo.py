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
import re
import glob
import robust_layer.simple_git
from . import util
from . import Bbki


class Repo:

    def __init__(self, bbki, path):
        self._bbki = bbki
        self._path = path

    def get_dir(self):
        return self._path

    def exists(self):
        return os.path.exists(self._path)

    def create(self):
        # Business exception should not be raise, but be printed as error message
        self.sync()

    def sync(self):
        # Business exception should not be raise, but be printed as error message
        robust_layer.simple_git.pull(self._path, reclone_on_failure=True, url="https://github.com/fpemud-os/bbki-repo")

    def check(self, autofix=False):
        if not self.exists():
            if autofix:
                self.create()
            else:
                raise RepoCheckError("repository does not exist")

    # def query_items(self):
    #     ret = []
    #     for fullfn in glob.glob(os.path.join(self._path, "**", "*.bbki")):
    #         ret.append(RepoItem.new_by_bbki_file(fullfn))
    #     return ret

    def query_item_type_name(self):
        ret = []
        for kernel_type in [Bbki.KERNEL_TYPE_LINUX]:
            kernelDir = os.path.join(self._path, kernel_type)
            if os.path.exists(kernelDir):
                for fn in os.listdir(kernelDir):
                    ret.append(Bbki.ITEM_TYPE_KERNEL, fn)
            kernelAddonDir = os.path.join(self._path, kernel_type + "-addon")
            if os.path.exists(kernelAddonDir):
                for fn in os.listdir(kernelAddonDir):
                    ret.append(Bbki.ITEM_TYPE_KERNEL_ADDON, fn)
        return ret

    def get_items_by_type_name(self, item_type, item_name):
        assert item_type in [Bbki.ITEM_TYPE_KERNEL, Bbki.ITEM_TYPE_KERNEL_ADDON]

        ret = []
        dirpath = os.path.join(self._path, _format_catdir(item_type, self._bbki.kernel_type), item_name)
        for fullfn in glob.glob(os.path.join(dirpath, "*.bbki")):
            ret.append(RepoItem.new_by_bbki_file(fullfn))
        return ret


class RepoItem:

    def __init__(self, repo):
        self._repo = repo
        self._itemType = None
        self._itemName = None
        self._ver = None
        self._rev = None

    @property
    def kernel_type(self):
        return self._repo._bbki._kernelType

    @property
    def item_type(self):
        return self._itemType

    @property
    def name(self):
        return self._itemName

    @property
    def fullname(self):
        return os.path.join(_format_catdir(self.item_type, self.kernel_type), self._itemName)

    @property
    def ver(self):
        return self._ver

    @property
    def rev(self):
        return self._rev

    @property
    def verstr(self):
        if self.revision == 0:
            return self.ver
        else:
            return self.ver + "-r" + self.revision

    @property
    def bbki_dir(self):
        return os.path.join(self._repo.get_dir(), self.fullname)

    @property
    def bbki_file(self):
        return os.path.join(self.bbki_dir, self.verstr + ".bbki")

    def get_variables(self):
        ret = dict()
        with open(self.bbki_file) as f:
            for line in f.split("\n"):
                line = line.rstrip()
                m = re.fullmatch(r'^(\S+)=(.*)', line)
                if m is not None:
                    k = m.group(1)
                    v = m.group(2)
                    if v.startswith("\"") and v.endswith("\""):
                        v = v[1:-1]
                    ret[k] = v
        return ret

    def call_function(self, function_name, *function_args):
        assert False

    @staticmethod
    def new_by_bbki_filepath(self, repo, bbki_file):
        assert repo is not None and isinstance(repo, Repo)
        assert bbki_file.startswith(repo.get_dir())

        bbki_file = bbki_file[len(repo.get_dir()):]
        catdir, itemName, fn = util.splitToTuple(bbki_file, "/", 3)
        itemType, kernelType = _parse_catdir(catdir)
        ver, rev = _parse_bbki_filename(fn)

        ret = RepoItem(repo)
        ret._itemType = itemType
        ret._itemName = itemName
        ret._ver = ver
        ret._rev = rev
        return ret


class RepoCheckError(Exception):

    def __init__(self, message):
        self.message = message


def _format_catdir(item_type, kernel_type):
    if item_type == Bbki.ITEM_TYPE_KERNEL:
        return kernel_type
    elif item_type == Bbki.ITEM_TYPE_KERNEL_ADDON:
        return kernel_type + "-addon"
    else:
        assert False


def _parse_catdir(catdir):
    if not catdir.endswith("-addon"):
        return (Bbki.ITEM_TYPE_KERNEL, catdir)
    else:
        return (Bbki.ITEM_TYPE_KERNEL_ADDON, catdir[:len("-addon") * -1])


def _parse_bbki_filename(filename):
    m = re.fullmatch("(.*)(-r([0-9]+))?", filename)
    if m.group(1) is None:
        return (m.group(1), 0)
    else:
        return (m.group(1), int(m.group(3)))
