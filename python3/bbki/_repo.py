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
from ._util import Util
from ._po import KernelType
from ._exception import RepoError


class Repo:

    ATOM_TYPE_KERNEL = 1
    ATOM_TYPE_KERNEL_ADDON = 2
    ATOM_TYPE_INITRAMFS = 3

    def __init__(self, bbki, path):
        self._bbki = bbki
        self._path = path

    @property
    def name(self):
        # FIXME
        return "main"

    def get_dir(self):
        return self._path

    def exists(self):
        return os.path.exists(self._path)

    def create(self):
        # Business exception should not be raise, but be printed as error message
        assert not self.exists()
        self.sync()

    def sync(self):
        # Business exception should not be raise, but be printed as error message
        robust_layer.simple_git.pull(self._path, reclone_on_failure=True, url="https://github.com/fpemud-os/bbki-repo")

    def check(self, autofix=False):
        if not self.exists():
            if autofix:
                self.create()
            else:
                raise RepoError("repository does not exist")

    # def query_items(self):
    #     ret = []
    #     for fullfn in glob.glob(os.path.join(self._path, "**", "*.bbki")):
    #         ret.append(RepoItem.new_by_bbki_file(fullfn))
    #     return ret

    def query_atom_type_name(self):
        ret = []
        for kernelType in [KernelType.LINUX]:
            kernelDir = os.path.join(self._path, kernelType)
            if os.path.exists(kernelDir):
                for fn in os.listdir(kernelDir):
                    ret.append((kernelType, self.ATOM_TYPE_KERNEL, fn))
            kernelAddonDir = os.path.join(self._path, kernelType + "-addon")
            if os.path.exists(kernelAddonDir):
                for fn in os.listdir(kernelAddonDir):
                    ret.append((kernelType, self.ATOM_TYPE_KERNEL_ADDON, fn))
            initramfsDir = os.path.join(self._path, kernelType + "-initramfs")
            if os.path.exists(initramfsDir):
                for fn in os.listdir(initramfsDir):
                    ret.append((kernelType, self.ATOM_TYPE_INITRAMFS, fn))
        return ret

    def get_atoms_by_type_name(self, kernel_type, atom_type, atom_name):
        assert atom_type in [self.ATOM_TYPE_KERNEL, self.ATOM_TYPE_KERNEL_ADDON, self.ATOM_TYPE_INITRAMFS]

        ret = []
        dirpath = os.path.join(self._path, _format_catdir(kernel_type, atom_type), atom_name)
        for fullfn in glob.glob(os.path.join(dirpath, "*.bbki")):
            ret.append(_new_atom_from_bbki_filepath(self, fullfn))
        return ret


class RepoAtom:

    def __init__(self, repo, kernel_type, atom_type, atom_name, ver, rev):
        self._bbki = repo._bbki
        self._repo = repo
        self._kernelType = kernel_type
        self._atomType = atom_type
        self._name = atom_name
        self._ver = ver
        self._rev = rev

    @property
    def kernel_type(self):
        return self._kernelType

    @property
    def atom_type(self):
        return self._atomType

    @property
    def name(self):
        return self._name

    @property
    def fullname(self):
        return os.path.join(_format_catdir(self._kernelType, self._atomType), self._name)

    @property
    def ver(self):
        return self._ver

    @property
    def rev(self):
        return self._rev

    @property
    def verstr(self):
        if self.rev == 0:
            return self.ver
        else:
            return self.ver + "-r" + self.rev

    @property
    def bbki_dir(self):
        return os.path.join(self._repo.get_dir(), self.fullname)

    @property
    def bbki_file(self):
        return os.path.join(self.bbki_dir, self.verstr + ".bbki")


def _format_catdir(kernel_type, atom_type):
    if atom_type == Repo.ATOM_TYPE_KERNEL:
        return kernel_type
    elif atom_type == Repo.ATOM_TYPE_KERNEL_ADDON:
        return kernel_type + "-addon"
    elif atom_type == Repo.ATOM_TYPE_INITRAMFS:
        return kernel_type + "-initramfs"
    else:
        assert False


def _parse_catdir(catdir):
    if catdir.endswith("-addon"):
        kernelType = catdir[:len("-addon") * -1]
        atomType = Repo.ATOM_TYPE_KERNEL_ADDON
    elif catdir.endswith("-initramfs"):
        kernelType = catdir[:len("-initramfs") * -1]
        atomType = Repo.ATOM_TYPE_INITRAMFS
    else:
        kernelType = catdir
        atomType = Repo.ATOM_TYPE_KERNEL
    assert kernelType in [KernelType.LINUX]
    return (kernelType, atomType)


def _parse_bbki_filename(filename):
    m = re.fullmatch(r'(.*)(-r([0-9]+))?\.bbki', filename)
    if m.group(2) is None:
        return (m.group(1), 0)
    else:
        return (m.group(1), int(m.group(3)))


def _new_atom_from_bbki_filepath(repo, bbki_file):
    assert repo is not None and isinstance(repo, Repo)
    assert bbki_file.startswith(repo.get_dir())

    bbki_file = bbki_file[len(repo.get_dir())+1:]               # /var/lib/bbki/linux/vanilla/5.13.8.bbki -> linux/vanilla/5.13.8.bbki
    catdir, atomName, fn = Util.splitToTuple(bbki_file, "/", 3)
    kernelType, atomType = _parse_catdir(catdir)
    ver, rev = _parse_bbki_filename(fn)

    ret = RepoAtom(repo, kernelType, atomType, atomName, ver, rev)
    ret._atomType = atomType
    ret._name = atomName
    ret._ver = ver
    ret._rev = rev
    return ret
