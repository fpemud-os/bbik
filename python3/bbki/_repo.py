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
import inspect
import urllib.parse
import robust_layer.simple_git
from ._util import Util
from ._util import TempChdir
from ._po import KernelType
from ._boot_entry import BootEntry
from .exception import RepoError


class Repo:

    ATOM_TYPE_KERNEL = 1
    ATOM_TYPE_KERNEL_ADDON = 2

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
                raise RepoError("repository does not exist")

    # def query_items(self):
    #     ret = []
    #     for fullfn in glob.glob(os.path.join(self._path, "**", "*.bbki")):
    #         ret.append(RepoItem.new_by_bbki_file(fullfn))
    #     return ret

    def query_atom_type_name(self):
        ret = []
        for kernel_type in [KernelType.LINUX]:
            kernelDir = os.path.join(self._path, kernel_type)
            if os.path.exists(kernelDir):
                for fn in os.listdir(kernelDir):
                    ret.append(self.ATOM_TYPE_KERNEL, fn)
            kernelAddonDir = os.path.join(self._path, kernel_type + "-addon")
            if os.path.exists(kernelAddonDir):
                for fn in os.listdir(kernelAddonDir):
                    ret.append(self.ATOM_TYPE_KERNEL_ADDON, fn)
        return ret

    def get_items_by_type_name(self, atom_type, item_name):
        assert atom_type in [self.ATOM_TYPE_KERNEL, self.ATOM_TYPE_KERNEL_ADDON]

        ret = []
        dirpath = os.path.join(self._path, _format_catdir(atom_type, self._bbki.config.get_kernel_type()), item_name)
        for fullfn in glob.glob(os.path.join(dirpath, "*.bbki")):
            ret.append(RepoAtom.new_by_bbki_filepath(fullfn))
        return ret


class RepoAtom:

    @staticmethod
    def new_by_bbki_filepath(self, repo, bbki_file):
        assert repo is not None and isinstance(repo, Repo)
        assert bbki_file.startswith(repo.get_dir())

        bbki_file = bbki_file[len(repo.get_dir()):]
        catdir, atomName, fn = Util.splitToTuple(bbki_file, "/", 3)
        atomType, kernelType = _parse_catdir(catdir)
        ver, rev = _parse_bbki_filename(fn)

        ret = RepoAtom(repo)
        ret._atomType = atomType
        ret._atomName = atomName
        ret._ver = ver
        ret._rev = rev
        return ret

    def __init__(self, repo):
        self._bbki = repo._bbki
        self._repo = repo
        self._atomType = None
        self._atomName = None
        self._ver = None
        self._rev = None

        self._tVarDict = None
        self._tFuncList = None

    @property
    def kernel_type(self):
        return self._repo._bbki._kernelType

    @property
    def atom_type(self):
        return self._atomType

    @property
    def name(self):
        return self._atomName

    @property
    def fullname(self):
        return os.path.join(_format_catdir(self.atom_type, self.kernel_type), self._atomName)

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
                    if m.group(1) in BbkiFileExecutor.get_valid_bbki_functions():
                        self._tFuncList.append(m.group(1))

        if "fetch" in self._tFuncList and "SRC_URI" in self._tVarDict:
            raise RepoError("fetch() and SRC_URI are mutally exclusive")
        if "fetch" in self._tFuncList and "SRC_URI_GIT" in self._tVarDict:
            raise RepoError("fetch() and SRC_URI_GIT are mutally exclusive")


class BbkiFileExecutor:

    @staticmethod
    def get_valid_bbki_functions():
        return [m[len("exec_"):] for m in dir(BbkiFileExecutor) if not m.startswith("exec_")]

    def __init__(self, item):
        self._bbki = item._bbki
        self._item = item

    def create_tmpdirs(self):
        self._tmpRootDir, self._trTmpDir, self._trWorkDir = _tmpdirs(self._item)
        if os.path.exists(self._tmpRootDir):
            robust_layer.simple_fops.rm(self._tmpRootDir)
        os.makedirs(self._trTmpDir)
        os.makedirs(self._trWorkDir)

    def remove_tmpdirs(self):
        robust_layer.simple_fops.rm(self._tmpRootDir)
        del self._trWorkDir
        del self._trTmpDir
        del self._tmpRootDir

    def get_workdir(self):
        return self._trWorkDir

    def get_tmpdir(self):
        return self._trTmpDir

    def exec_fetch(self):
        if self._item_has_me():
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

    def exec_src_unpack(self):
        if self._item_has_me():
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

    def exec_src_prepare(self):
        if self._item_has_me():
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

    def exec_kernel_build(self):
        if self._item.atom_type != self.ATOM_TYPE_KERNEL:
            raise NotImplementedError()

        if self._item_has_me():
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
                if self._item.kernel_type == KernelType.LINUX:
                    optList = []
                    optList.append("CFLAGS=\"-Wno-error\"")
                    optList.append(self._bbki.config.get_build_variable("MAKEOPTS"))
                    Util.shellCall("/usr/bin/make %s" % (" ".join(optList)))
                    Util.shellCall("/usr/bin/make %s modules" % (" ".join(optList)))
                else:
                    assert False

    def exec_kernel_install(self):
        if self._item.atom_type != self.ATOM_TYPE_KERNEL:
            raise NotImplementedError()

        if self._item_has_me():
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += "A='%s'\n" % ("' '".join(_distfiles_get(self._item)))
                cmd += "WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._item.bbki_file)
                cmd += "\n"
                cmd += "kernel_install\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            with TempChdir(self._trWorkDir):
                if self._item.kernel_type == KernelType.LINUX:
                    bootEntry = BootEntry.new_from_kernel_srcdir(self._bbki, "native", self._trWorkDir)
                    shutil.copy("arch/%s/boot/bzImage" % (bootEntry.arch), bootEntry.kernel_file)
                    shutil.copy(os.path.join(self._trWorkDir, ".config"), bootEntry.kernel_config_file)
                    # shutil.copy(os.path.join(self._trWorkDir, "System.map"), bootEntry.kernelMapFile)       # FIXME
                else:
                    assert False

    def exec_kernel_addon_patch_kernel(self, kernel_item):
        if self._item.atom_type != self.ATOM_TYPE_KERNEL_ADDON:
            raise NotImplementedError()

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_item)
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

    def exec_kernel_addon_contribute_config_rules(self, kernel_item):
        if self._item.atom_type != self.ATOM_TYPE_KERNEL_ADDON:
            raise NotImplementedError()

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_item)
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

    def exec_kernel_addon_build(self, kernel_item):
        if self._item.atom_type != self.ATOM_TYPE_KERNEL_ADDON:
            raise NotImplementedError()

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_item)
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

    def exec_kernel_addon_install(self, kernel_item):
        if self._item.atom_type != self.ATOM_TYPE_KERNEL_ADDON:
            raise NotImplementedError()

        if self._item_has_me():
            # custom action
            pass
        else:
            # no-op as the default action
            pass

    def _item_has_me(self):
        parent_func_name = inspect.getouterframes(inspect.currentframe())[1].function
        assert parent_func_name.startswith("exec_")
        return self._item.has_function(parent_func_name[len("exec_"):])


def _format_catdir(atom_type, kernel_type):
    if atom_type == Repo.ATOM_TYPE_KERNEL:
        return kernel_type
    elif atom_type == Repo.ATOM_TYPE_KERNEL_ADDON:
        return kernel_type + "-addon"
    else:
        assert False


def _parse_catdir(catdir):
    if not catdir.endswith("-addon"):
        return (Repo.ATOM_TYPE_KERNEL, catdir)
    else:
        return (Repo.ATOM_TYPE_KERNEL_ADDON, catdir[:len("-addon") * -1])


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
    # trBuildInfoDir = os.path.join(tmpRootDir, "build-info")     # FIXME
    # trDistDir = os.path.join(tmpRootDir, "distdir")             # FIXME
    # trEmptyDir = os.path.join(tmpRootDir, "empty")              # FIXME
    # trFilesDir = os.path.join(tmpRootDir, "files")              # should be symlink
    # trHomeDir = os.path.join(tmpRootDir, "homedir")             # FIXME
    trTmpDir = os.path.join(tmpRootDir, "temp")
    trWorkDir = os.path.join(tmpRootDir, "work")
    return (tmpRootDir, trTmpDir, trWorkDir)
