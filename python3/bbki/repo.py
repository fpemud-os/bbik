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
import shutil
import urllib.parse
import robust_layer.simple_git
from . import Bbki
from . import BbkiRepoError
from .util import TempChdir, Util


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
                raise BbkiRepoError("repository does not exist")

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

    def __init__(self, repo):
        self._bbki = repo._bbki
        self._repo = repo
        self._itemType = None
        self._itemName = None
        self._ver = None
        self._rev = None

        self._tVarDict = None
        self._tFuncList = None

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
        self._fillt()                           # fill cache
        return self._tVarDict                   # return value according to cache

    def has_variable(self, var_name):
        self._fillt()                           # fill cache
        return var_name in self._tVarDict       # return value according to cache

    def get_variable(self, var_name):
        self._fillt()                           # fill cache
        return self._tVarDict[var_name]         # return value according to cache

    def get_functions(self):
        self._fillt()                           # fill cache
        return self._tFuncList                  # return value according to cache

    def has_function(self, func_name):
        self._fillt()                           # fill cache
        return func_name in self._tFuncList     # return value according to cache

    def get_distfiles(self):
        if self.has_function("fetch"):
            return [_custom_src_dir(self)]
        else:
            ret = []
            ret += [localFn for url, localFn in _distfiles_get(self)]
            ret += [localFn for url, localFn in _distfiles_get_git(self)]
            return ret

    def _fillt(self):
        if self._tVarDict is not None and self._tFuncList is not None:
            return

        self._tVarDict = dict()
        with open(self.bbki_file) as f:
            for line in f.split("\n"):
                line = line.rstrip()
                m = re.fullmatch(r'^(\S+)=(.*)', line)
                if m is not None:
                    k = m.group(1)
                    v = m.group(2)
                    if v.startswith("\"") and v.endswith("\""):
                        v = v[1:-1]
                    self._tVarDict[k] = v

        self._tFuncList = []
        with open(self.bbki_file) as f:
            for line in f.split("\n"):
                line = line.rstrip()
                m = re.fullmatch(r'^(\S+)\(\) {', line)
                if m is not None:
                    if m.group(1) in _BbkiFileExecutor.get_valid_bbki_functions():
                        self._tFuncList.append(m.group(1))

        if "fetch" in self._tFuncList and "SRC_URI" in self._tVarDict:
            raise BbkiRepoError("fetch() and SRC_URI are mutally exclusive")
        if "fetch" in self._tFuncList and "SRC_URI_GIT" in self._tVarDict:
            raise BbkiRepoError("fetch() and SRC_URI_GIT are mutally exclusive")


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


def _custom_src_dir(item):
    return os.path.join("custom-src", item.bbki_dir)


def _distfiles_get(item):
    if not item.has_variable("SRC_URI"):
        return []

    assert not item.has_function("fetch")
    ret = []
    for line in item.get_variable("SRC_URI").split("\n"):
        line = line.strip()
        if line != "":
            ret.append((line, os.path.basename(line)))
    return ret


def _distfiles_get_git(item):
    if not item.has_variable("SRC_URI_GIT"):
        return []

    assert not item.has_function("fetch")
    ret = []
    for line in item.get_variable("SRC_URI_GIT").split("\n"):
        line = line.strip()
        if line != "":
            ret.append((line, "git-src" + urllib.parse.urlparse(line).path))
    return ret


def _tmpdirs(item):
    tmpRootDir = os.path.join(item._bbki.config.tmp_dir, item.bbki_dir)
    trBuildInfoDir = os.path.join(tmpRootDir, "build-info")     # FIXME
    trDistDir = os.path.join(tmpRootDir, "distdir")             # FIXME
    trEmptyDir = os.path.join(tmpRootDir, "empty")              # FIXME
    trFilesDir = os.path.join(tmpRootDir, "files")              # should be symlink
    trHomeDir = os.path.join(tmpRootDir, "homedir")             # FIXME
    trTmpDir = os.path.join(tmpRootDir, "temp")
    trWorkDir = os.path.join(tmpRootDir, "work")
    return (tmpRootDir, trTmpDir, trWorkDir)


class _BbkiFileExecutor:

    @staticmethod
    def get_valid_bbki_functions():
        ret = dir(_BbkiFileExecutor)
        ret = [m for m in ret if callable(getattr(_BbkiFileExecutor, m))]
        ret = [m for m in ret if not m.startswith("_")]
        ret.remove("get_valid_bbki_functions")
        return ret

    def __init__(self, item, kernel_item=None):
        if item.item_type == Bbki.ITEM_TYPE_KERNEL:
            assert kernel_item is not None
        elif item.item_type == Bbki.ITEM_TYPE_KERNEL_ADDON:
            assert kernel_item is None
        else:
            assert False

        self._bbki = item._bbki
        self._item = item
        self._kernel_item = kernel_item
        self._tmpRootDir, self._trTmpDir, self._trWorkDir = _tmpdirs(self._item)

    def fetch(self):
        if self._item.has_function("fetch"):                                                                
            # custom action
            targetDir = os.path.join(self._bbki.config.cache_distfiles_dir, _custom_src_dir(self._item))
            os.makedirs(targetDir, exist_ok=True)
            with TempChdir(targetDir):
                cmd = ""
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "fetch\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:                                                                                                   
            # default action
            for url, localFn in _distfiles_get(self._item):
                localFullFn = os.path.join(self._bbki.config.cache_distfiles_dir, localFn)
                if not os.path.exists(localFullFn):
                    robust_layer.wget.exec("-O", localFullFn, url)
            for url, localFn in _distfiles_get_git(self._item):
                robust_layer.simple_git.pull(localFullFn, reclone_on_failure=True, url=url)

    def src_unpack(self):
        self._ensure_tmpdir()
        if self._item.has_function("src_unpack"):                                                           
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += "A='%s'\n" % ("' '".join(_distfiles_get(self._item)))
                cmd += "WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "src_unpack\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:                                                                                               
            # default action
            for url, localFn in _distfiles_get(self._item):
                localFullFn = os.path.join(self._bbki.config.cache_distfiles_dir, localFn)
                try:
                    shutil.unpack_archive(localFullFn, self._trWorkDir)
                except ValueError:
                    pass

    def src_prepare(self):
        self._ensure_tmpdir()
        if self._item.has_function("src_prepare"):                                                           
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += "A='%s'\n" % ("' '".join(_distfiles_get(self._item)))
                cmd += "WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "src_prepare\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:                                                                                               
            # no-op as the default action
            pass

    def kernel_build(self):
        if self._item.item_type != Bbki.ITEM_TYPE_KERNEL:
            raise NotImplementedError()

        self._ensure_tmpdir()
        if self._item.has_function("kernel_build"):                                                           
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += "A='%s'\n" % ("' '".join(_distfiles_get(self._item)))
                cmd += "WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "kernel_build\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:                                                                                               
            # default action
            with TempChdir(self._trWorkDir):
                optList = []
                optList.append("CFLAGS=\"-Wno-error\"")
                optList.append(self._bbki.config.get_make_conf_variable("MAKEOPTS"))
                Util.shellCall("/usr/bin/make %s" % (" ".join(optList)))

    def kernel_addon_patch_kernel(self):
        if self._item.item_type != Bbki.ITEM_TYPE_KERNEL_ADDON:
            raise NotImplementedError()

        self._ensure_tmpdir()
        if self._item.has_function("kernel_addon_patch_kernel"):                                                           
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(self._kernel_item)
            with TempChdir(kernelDir):
                cmd = ""
                cmd += "A='%s'\n" % ("' '".join(_distfiles_get(self._item)))
                cmd += "WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "kernel_addon_patch_kernel\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:                                                                                               
            # no-op as the default action
            pass

    def kernel_addon_build(self):
        if self._item.item_type != Bbki.ITEM_TYPE_KERNEL_ADDON:
            raise NotImplementedError()

        if self._item.has_function("kernel_addon_build"):                                                           
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(self._kernel_item)
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += "A='%s'\n" % ("' '".join(_distfiles_get(self._item)))
                cmd += "WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "kernel_addon_build\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:                                                                                               
            # no-op as the default action
            pass

    def _ensure_tmpdir(self):
        os.makedirs(self._trTmpDir, exists_ok=True)
        os.makedirs(self._trWorkDir, exists_ok=True)
