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
import shutil
import inspect
import pathlib
import tarfile
import zipfile
import platform
import urllib.parse
import robust_layer.simple_git
import robust_layer.simple_fops
from ._util import Util
from ._util import TempChdir
from ._repo import Repo
from ._exception import RepoError
from ._initramfs import InitramfsInstaller


class BbkiAtomExecutor:

    @staticmethod
    def get_valid_bbki_functions():
        return [m[len("exec_"):] for m in dir(BbkiAtomExecutor) if m.startswith("exec_")]

    def __init__(self, bbki, atom):
        self._bbki = bbki
        self._atom = atom
        self._tVarDict = None
        self._tFuncList = None
        self._tmpRootDir, self._trTmpDir, self._trWorkDir = _tmpdirs(self._bbki, self._atom)

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

    def get_files_dir(self):
        return os.path.join(self._atom.bbki_dir, "files")

    def get_work_dir(self):
        return self._trWorkDir

    def get_tmp_dir(self):
        return self._trTmpDir

    def run_for_variable_values(self, varList):
        out = None
        robust_layer.simple_fops.mkdir(self._bbki._cfg.tmp_dir)
        with TempChdir(self._bbki._cfg.tmp_dir):
            cmd = ""
            cmd += self._vars_common()
            cmd += "source %s\n" % (self._atom.bbki_file)
            for var in varList:
                cmd += "echo %s=${%s}\n" % (var, var)
            out = Util.cmdCall("/bin/bash", "-c", cmd)

        ret = dict()
        for line in out.split("\n"):
            m = re.fullmatch(r'^(\S+?)=(.*)', line)
            if m is not None:
                ret[m.group(1)] = m.group(2)
        return ret

    def create_tmpdirs(self):
        if os.path.exists(self._tmpRootDir):
            robust_layer.simple_fops.rm(self._tmpRootDir)
        os.makedirs(self._trTmpDir)
        os.makedirs(self._trWorkDir)

    def remove_tmpdirs(self):
        robust_layer.simple_fops.rm(self._tmpRootDir)

    def exec_fetch(self):
        if self._item_has_me():
            # custom action
            targetDir = os.path.join(self._bbki._cfg.cache_distfiles_dir, _custom_src_dir(self._atom))
            os.makedirs(targetDir, exist_ok=True)
            with TempChdir(targetDir):
                cmd = ""
                cmd += self._vars_common()
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "fetch\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            for downloadType, url, localFn in _distfiles_get(self._atom):
                localFullFn = os.path.join(self._bbki._cfg.cache_distfiles_dir, localFn)
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
                cmd += self._vars_common()
                cmd += self._vars_after_fetch()
                cmd += "source %s\n" % (self._atom.bbki_file)
                cmd += "src_unpack\n"
                Util.cmdCall("/bin/bash", "-c", cmd)
        else:
            # default action
            for downloadType, url, localFn in _distfiles_get(self._atom):
                localFullFn = os.path.join(self._bbki._cfg.cache_distfiles_dir, localFn)
                if os.path.isdir(localFullFn):
                    Util.shellCall("cp -r %s/* %s" % (localFullFn, self._trWorkDir))
                elif tarfile.is_tarfile(localFullFn) or zipfile.is_zipfile(localFullFn):
                    shutil.unpack_archive(localFullFn, self._trWorkDir)
                else:
                    Util.shellCall("cp %s %s" % (localFullFn, self._trWorkDir))

    def exec_src_prepare(self):
        if not self._item_has_me():
            return

        with TempChdir(self._trWorkDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "src_prepare\n"
            Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_kernel_install(self, kernelConfigFile, kernelConfigRulesFile, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL)

        if not self._item_has_me():
            return

        with TempChdir(self._trWorkDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += "export MAKEOPTS='%s'\n" % (self._bbki._cfg.get_build_variable("MAKEOPTS"))
            cmd += 'export PATH="%s:$PATH"\n' % (_get_script_helpers_dir())
            cmd += "export KVER='%s'\n" % (boot_entry.verstr)
            cmd += "export KERNEL_CONFIG_FILE='%s'\n" % (kernelConfigFile)
            cmd += 'export PATH="%s:$PATH"\n' % (_get_script_helpers_dir())
            cmd += "\n"
            cmd += "export _KENREL_CONFIG_RULES_FILE='%s'\n" % (kernelConfigRulesFile)      # FIXME
            cmd += "\n"
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "\n"
            cmd += "kernel_install\n"
            Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_kernel_cleanup(self, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL)

        if not self._item_has_me():
            return

        with TempChdir(self._trWorkDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += 'export PATH="%s:$PATH"\n' % (_get_script_helpers_dir())
            cmd += "export KVER='%s'\n" % (boot_entry.verstr)
            cmd += "export KERNEL_MODULES_DIR='%s'\n" % (self._bbki._fsLayout.get_kernel_modules_dir(boot_entry.verstr))
            cmd += "\n"
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "\n"
            cmd += "kernel_cleanup\n"
            Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_kernel_addon_patch_kernel(self, kernel_atom, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if not self._item_has_me():
            return

        dummy, dummy, kernelDir = _tmpdirs(self._bbki, kernel_atom)
        with TempChdir(kernelDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += "export KVER='%s'\n" % (boot_entry.verstr)
            cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
            cmd += "\n"
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "\n"
            cmd += "kernel_addon_patch_kernel\n"
            Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_kernel_addon_contribute_config_rules(self, kernel_atom, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if not self._item_has_me():
            return ""

        dummy, dummy, kernelDir = _tmpdirs(self._bbki, kernel_atom)
        with TempChdir(self._trWorkDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += "export KVER='%s'\n" % (boot_entry.verstr)
            cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
            cmd += "\n"
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "\n"
            cmd += "kernel_addon_contribute_config_rules\n"
            return Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_kernel_addon_install(self, kernel_atom, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if not self._item_has_me():
            return

        dummy, dummy, kernelDir = _tmpdirs(self._bbki, kernel_atom)
        with TempChdir(self._trWorkDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += "export KVER='%s'\n" % (boot_entry.verstr)
            cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
            cmd += "export KERNEL_MODULES_DIR='%s'\n" % (self._bbki._fsLayout.get_kernel_modules_dir(boot_entry.verstr))
            cmd += "export FIRMWARE_DIR='%s'\n" % (self._bbki._fsLayout.get_firmware_dir())
            cmd += "export MAKEOPTS='%s'\n" % (self._bbki._cfg.get_build_variable("MAKEOPTS"))
            cmd += 'export PATH="%s:$PATH"\n' % (_get_script_helpers_dir())
            cmd += "\n"
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "\n"
            cmd += "kernel_addon_install\n"
            Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_kernel_addon_cleanup(self):
        self._restrict_atom_type(Repo.ATOM_TYPE_KERNEL_ADDON)

        if not self._item_has_me():
            return

    def exec_initramfs_contribute_config_rules(self, kernel_atom, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_INITRAMFS)

        if not self._item_has_me():
            return ""

        dummy, dummy, kernelDir = _tmpdirs(self._bbki, kernel_atom)
        with TempChdir(kernelDir):
            cmd = ""
            cmd += self._vars_common()
            cmd += self._vars_after_fetch()
            cmd += "export KVER='%s'\n" % (boot_entry.verstr)
            cmd += "export KERNEL_DIR='%s'\n" % (kernelDir)
            cmd += "\n"
            cmd += "source %s\n" % (self._atom.bbki_file)
            cmd += "\n"
            cmd += "initramfs_contribute_config_rules\n"
            return Util.cmdCall("/bin/bash", "-c", cmd)

    def exec_initramfs_install(self, boot_entry):
        self._restrict_atom_type(Repo.ATOM_TYPE_INITRAMFS)

        # if self._item_has_me():
        if False:
            # custom action
            with TempChdir(self._trWorkDir):
                cmd = ""
                cmd += self._vars_common()
                cmd += self._vars_after_fetch()
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
            InitramfsInstaller(self._bbki, self._trWorkDir, boot_entry).install()

    def _fillt(self):
        if self._tVarDict is not None and self._tFuncList is not None:
            return

        lineList = pathlib.Path(self._atom.bbki_file).read_text().split("\n")
        lineList = [x.rstrip() for x in lineList]

        self._tVarDict = dict()
        for line in lineList:
            m = re.fullmatch(r'^(\S+?)=.*', line)
            if m is not None:
                k = m.group(1)
                self._tVarDict[k] = None
        self._tVarDict = self.run_for_variable_values(self._tVarDict.keys())

        self._tFuncList = []
        for line in lineList:
            m = re.fullmatch(r'^(\S+)\(\) {', line)
            if m is not None:
                if m.group(1) in BbkiAtomExecutor.get_valid_bbki_functions():
                    self._tFuncList.append(m.group(1))

        if "fetch" in self._tFuncList and "SRC_URI" in self._tVarDict:
            raise RepoError("fetch() and SRC_URI are mutally exclusive")

    def _restrict_atom_type(self, *atomTypes):
        if self._atom.atom_type not in atomTypes:
            raise NotImplementedError()

    def _item_has_me(self):
        parent_func_name = inspect.getouterframes(inspect.currentframe())[1].function
        assert parent_func_name.startswith("exec_")
        return self._atom.has_function(parent_func_name[len("exec_"):])

    def _vars_common(self):
        buf = ""
        if True:
            buf += "export P='%s-%s'\n" % (self._atom.name, self._atom.ver)
            buf += "export PN='%s'\n" % (self._atom.name)
            buf += "export PV='%s'\n" % (self._atom.ver)
        if True:
            buf += "export ARCH='%s'\n" % (platform.machine())
        if True:
            buf += "export FILESDIR='%s'\n" % (self.get_files_dir())
            buf += "export WORKDIR='%s'\n" % (self._trWorkDir)
        return buf

    def _vars_after_fetch(self):
        buf = ""
        if True:
            fnlist = [localFn for downloadType, url, localFn in _distfiles_get(self._atom)]
            fnlist = [os.path.join(os.path.join(self._bbki._cfg.cache_distfiles_dir, x)) for x in fnlist]
            buf += "export A='%s'\n" % ("' '".join(fnlist))
        return buf


def _get_script_helpers_dir():
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "script-helpers")


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
            assert "->" not in line
            ret.append(("git", line, "git-src" + urllib.parse.urlparse(line).path))
        elif line.startswith("git+http://") or line.startswith("git+https://"):
            assert "->" not in line
            ret.append(("git", line[len("git+"):], "git-src" + urllib.parse.urlparse(line).path))
        else:
            tlist = line.split(" -> ")
            if len(tlist) == 1:
                tlist.append(os.path.basename(line))
            elif len(tlist) == 2:
                pass
            else:
                assert False
            ret.append(("wget", tlist[0], tlist[1]))
    return ret


def _tmpdirs(bbki, atom):
    tmpRootDir = os.path.join(bbki._cfg.tmp_dir, atom.fullname)
    # trBuildInfoDir = os.path.join(tmpRootDir, "build-info")     # FIXME
    # trDistDir = os.path.join(tmpRootDir, "distdir")             # FIXME
    # trEmptyDir = os.path.join(tmpRootDir, "empty")              # FIXME
    # trFilesDir = os.path.join(tmpRootDir, "files")              # should be symlink
    # trHomeDir = os.path.join(tmpRootDir, "homedir")             # FIXME
    trTmpDir = os.path.join(tmpRootDir, "temp")
    trWorkDir = os.path.join(tmpRootDir, "work")
    return (tmpRootDir, trTmpDir, trWorkDir)
