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
import pathlib
import tarfile
import zipfile
import urllib.parse
import pkg_resources
import robust_layer.simple_git
import robust_layer.simple_fops
from ._util import Util
from ._util import TempChdir
from ._po import KernelType
from ._boot_entry import BootEntry
from ._exception import RepoError
from ._initramfs import InitramfsInstaller


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

        self._tVarDict = None
        self._tFuncList = None

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
            return [localFn for downloadType, url, localFn in _distfiles_get(self)]

    def _fillt(self):
        if self._tVarDict is not None and self._tFuncList is not None:
            return

        lineList = pathlib.Path(self.bbki_file).read_text().split("\n")
        lineList = [x.rstrip() for x in lineList]

        self._tVarDict = dict()
        for line in lineList:
            m = re.fullmatch(r'^(\S+)=(.*)', line)
            if m is not None:
                k = m.group(1)
                v = m.group(2)
                if v.startswith("\"") and v.endswith("\""):
                    v = v[1:-1]
                self._tVarDict[k] = v

        self._tFuncList = []
        for line in lineList:
            m = re.fullmatch(r'^(\S+)\(\) {', line)
            if m is not None:
                if m.group(1) in BbkiAtomExecutor.get_valid_bbki_functions():
                    self._tFuncList.append(m.group(1))

        if "fetch" in self._tFuncList and "SRC_URI" in self._tVarDict:
            raise RepoError("fetch() and SRC_URI are mutally exclusive")


class BbkiAtomExecutor:

    @staticmethod
    def get_valid_bbki_functions():
        return [m[len("exec_"):] for m in dir(BbkiAtomExecutor) if m.startswith("exec_")]

    def __init__(self, atom):
        self._bbki = atom._bbki
        self._atom = atom

    def create_tmpdirs(self):
        self._tmpRootDir, self._trTmpDir, self._trWorkDir = _tmpdirs(self._atom)
        if os.path.exists(self._tmpRootDir):
            robust_layer.simple_fops.rm(self._tmpRootDir)
        os.makedirs(self._trTmpDir)
        os.makedirs(self._trWorkDir)

    def remove_tmpdirs(self):
        robust_layer.simple_fops.rm(self._tmpRootDir)
        del self._trWorkDir
        del self._trTmpDir
        del self._tmpRootDir

    def get_files_dir(self):
        return os.path.join(self._atom.bbki_dir, "files")

    def get_work_dir(self):
        return self._trWorkDir

    def get_tmp_dir(self):
        return self._trTmpDir

    def exec_fetch(self):
        if self._item_has_me():
            # custom action
            targetDir = os.path.join(self._bbki.config.cache_distfiles_dir, _custom_src_dir(self._atom))
            os.makedirs(targetDir, exist_ok=True)
            with TempChdir(targetDir):
                cmd = ""
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "fetch\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            for downloadType, url, localFn in _distfiles_get(self._atom):
                localFullFn = os.path.join(self._bbki.config.cache_distfiles_dir, localFn)
                os.makedirs(os.path.dirname(localFullFn), exist_ok=True)
                if downloadType == "git":
                    robust_layer.simple_git.pull(localFullFn, reclone_on_failure=True, url=url)
                elif downloadType == "wget":
                    if not os.path.exists(localFullFn):
                        os.makedirs(os.path.dirname(localFullFn), exist_ok=True)
                        robust_layer.wget.exec("-O", localFullFn, url)
                else:
                    assert False

    def exec_src_unpack(self):
        if self._item_has_me():
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "src_unpack\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            for downloadType, url, localFn in _distfiles_get(self._atom):
                localFullFn = os.path.join(self._bbki.config.cache_distfiles_dir, localFn)
                if os.path.isdir(localFullFn):
                    Util.shellCall("cp -r %s/* %s" % (localFullFn, self._trWorkDir))
                elif tarfile.is_tarfile(localFullFn) or zipfile.is_zipfile(localFullFn):
                    shutil.unpack_archive(localFullFn, self._trWorkDir)
                else:
                    Util.shellCall("cp %s %s" % (localFullFn, self._trWorkDir))

    def exec_src_prepare(self):
        if self._item_has_me():
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "src_prepare\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # no-op as the default action
            pass

    def exec_kernel_build(self):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL)

        if self._item_has_me():
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export MAKEOPTS='%s'\n" % (self._bbki.config.get_build_variable("MAKEOPTS"))
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "kernel_build\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            with TempChdir(self._trWorkDir):
                if self._atom.kernel_type == KernelType.LINUX:
                    optList = []
                    optList.append("CFLAGS=\"-Wno-error\"")
                    optList.append(self._bbki.config.get_build_variable("MAKEOPTS"))
                    Util.shellCall("make %s" % (" ".join(optList)))
                    Util.shellCall("make %s modules" % (" ".join(optList)))
                else:
                    assert False

    def exec_kernel_install(self):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL)

        if self._item_has_me():
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += 'export PATH="%s:$PATH"\n' % (_get_script_helpers_dir())
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "kernel_install\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            with TempChdir(self._trWorkDir):
                if self._atom.kernel_type == KernelType.LINUX:
                    bootEntry = _new_boot_entry_from_kernel_srcdir(self._bbki, self._trWorkDir)
                    shutil.copy("arch/%s/boot/bzImage" % (bootEntry.arch), bootEntry.kernel_filepath)
                    shutil.copy(os.path.join(self._trWorkDir, ".config"), bootEntry.kernel_config_filepath)
                    shutil.copy(os.path.join(self._trWorkDir, "config.rules"), bootEntry.kernel_config_rules_filepath)
                    robust_layer.simple_fops.rm(bootEntry.kernel_modules_dirpath)
                    Util.shellCall("make modules_install")
                    # shutil.copy(os.path.join(self._trWorkDir, "System.map"), bootEntry.kernelMapFile)       # FIXME
                else:
                    assert False

    def exec_kernel_addon_patch_kernel(self, kernel_atom):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_atom)
            with TempChdir(kernelDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export KVER='%s'\n" % (kernel_atom.verstr)
                cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "kernel_addon_patch_kernel\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # no-op as the default action
            pass

    def exec_kernel_addon_contribute_config_rules(self, kernel_atom):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_atom)
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export KVER='%s'\n" % (kernel_atom.verstr)
                cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "kernel_addon_contribute_config_rules\n"
                return Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # no-op as the default action
            return ""

    def exec_kernel_addon_build(self, kernel_atom):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_atom)
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export KVER='%s'\n" % (kernel_atom.verstr)
                cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "export MAKEOPTS='%s'\n" % (self._bbki.config.get_build_variable("MAKEOPTS"))
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "kernel_addon_build\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # no-op as the default action
            pass

    def exec_kernel_addon_install(self, kernel_atom):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_atom)
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export KVER='%s'\n" % (kernel_atom.verstr)
                cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "export KERNEL_MODULES_DIR='%s'\n" % (self._bbki._fsLayout.get_kernel_modules_dir(kernel_atom.verstr))
                cmd += "export FIRMWARE_DIR='%s'\n" % (self._bbki._fsLayout.get_firmware_dir())
                cmd += 'export PATH="%s:$PATH"\n' % (_get_script_helpers_dir())
                cmd += "\n"
                cmd += "source %s\n" % (pkg_resources.resource_filename(__name__, os.path.join("script-helpers", "do_fw")))
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "kernel_addon_install\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # no-op as the default action
            pass

    def exec_initramfs_contribute_config_rules(self, kernel_atom):
        self._restrict_atom_type(Repo.ATOM_TYPE_INITRAMFS)

        if self._item_has_me():
            # custom action
            dummy, dummy, kernelDir = _tmpdirs(kernel_atom)
            with TempChdir(kernelDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export KVER='%s'\n" % (kernel_atom.verstr)
                cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "initramfs_contribute_config_rules\n"
                return Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # no-op as the default action
            return ""

    def exec_initramfs_install(self, host_storage, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_INITRAMFS)

        if self._item_has_me():
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._common_vars()
                cmd += "export WORKDIR='%s'\n" % (self._trWorkDir)
                cmd += "export KERNEL_CONFIG_FILE='%s'\n" % (boot_entry.kernel_config_filepath)
                cmd += "export KERNEL_MODULES_DIR='%s'\n" % (boot_entry.kernel_modules_dirpath)
                cmd += "export FIRMWARE_DIR='%s'\n" % (boot_entry.firmware_dirpath)
                cmd += "\n"
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "\n"
                cmd += "initramfs_install\n"
                return Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # FIXME
            InitramfsInstaller(self._bbki, self._trWorkDir, host_storage, boot_entry).install()

    def _restrict_atom_type(self, *atomTypes):
        if self._atom.atom_type not in atomTypes:
            raise NotImplementedError()

    def _item_has_me(self):
        parent_func_name = inspect.getouterframes(inspect.currentframe())[1].function
        assert parent_func_name.startswith("exec_")
        return self._atom.has_function(parent_func_name[len("exec_"):])

    def _common_vars(self):
        buf = ""
        if True:
            fnlist = [localFn for downloadType, url, localFn in _distfiles_get(self._atom)]
            fnlist = [os.path.join(os.path.join(self._bbki.config.cache_distfiles_dir, x)) for x in fnlist]
            buf += "export A='%s'\n" % ("' '".join(fnlist))
        if True:
            buf += "export FILESDIR='%s'\n" % (self.get_files_dir())
        return buf


def _get_script_helpers_dir():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "script-helpers")


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


def _custom_src_dir(atom):
    return os.path.join("custom-src", atom.fullname)


def _distfiles_get(atom):
    if not atom.has_variable("SRC_URI"):
        return []

    assert not atom.has_function("fetch")

    ret = []
    for line in atom.get_variable("SRC_URI").split("\n"):
        line = line.strip()
        if line == "":
            continue
        if line.startswith("git://"):
            ret.append(("git", line, "git-src" + urllib.parse.urlparse(line).path))
        elif line.startswith("git+http://") or line.startswith("git+https://"):
            ret.append(("git", line[len("git+"):], "git-src" + urllib.parse.urlparse(line).path))
        else:
            ret.append(("wget", line, os.path.basename(line)))
    return ret


def _tmpdirs(atom):
    tmpRootDir = os.path.join(atom._bbki.config.tmp_dir, atom.fullname)
    # trBuildInfoDir = os.path.join(tmpRootDir, "build-info")     # FIXME
    # trDistDir = os.path.join(tmpRootDir, "distdir")             # FIXME
    # trEmptyDir = os.path.join(tmpRootDir, "empty")              # FIXME
    # trFilesDir = os.path.join(tmpRootDir, "files")              # should be symlink
    # trHomeDir = os.path.join(tmpRootDir, "homedir")             # FIXME
    trTmpDir = os.path.join(tmpRootDir, "temp")
    trWorkDir = os.path.join(tmpRootDir, "work")
    return (tmpRootDir, trTmpDir, trWorkDir)


def _new_boot_entry_from_kernel_srcdir(bbki, kernel_srcdir):
    version = None
    patchlevel = None
    sublevel = None
    extraversion = None
    with open(os.path.join(kernel_srcdir, "Makefile")) as f:
        buf = f.read()

        m = re.search("VERSION = ([0-9]+)", buf, re.M)
        if m is None:
            raise ValueError("illegal kernel source directory")
        version = int(m.group(1))

        m = re.search("PATCHLEVEL = ([0-9]+)", buf, re.M)
        if m is None:
            raise ValueError("illegal kernel source directory")
        patchlevel = int(m.group(1))

        m = re.search("SUBLEVEL = ([0-9]+)", buf, re.M)
        if m is None:
            raise ValueError("illegal kernel source directory")
        sublevel = int(m.group(1))

        m = re.search("EXTRAVERSION = (\\S+)", buf, re.M)
        if m is not None:
            extraversion = m.group(1)

    if extraversion is not None:
        verstr = "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
    else:
        verstr = "%d.%d.%d" % (version, patchlevel, sublevel)
    return BootEntry(bbki, os.uname().machine, verstr)


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
