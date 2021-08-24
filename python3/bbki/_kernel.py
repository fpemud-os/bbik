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
import kmod
import shutil
import pylkcutil
import pkg_resources
from ._util import Util
from ._util import TempChdir
from ._boot_dir import BootEntry
from ._repo import BbkiFileExecutor


class KernelInstaller:

    def __init__(self, bbki, kernel_atom, kernel_atom_item_list):
        self._bbki = bbki

        self._kernelAtom = kernel_atom
        self._addonAtomList = kernel_atom_item_list

        self._executorDict = dict()
        self._executorDict[kernel_atom] = BbkiFileExecutor(kernel_atom)
        for item in kernel_atom_item_list:
            self._executorDict[item] = BbkiFileExecutor(item)

        self._progress = KernelInstallProgress.STEP_INIT
        self._targetBootEntry = BootEntry.new_from_verstr(self._bbki, os.uname().machine, self._kernelAtom.verstr)
        self._kcfgRulesTmpFile = None
        self._dotCfgFile = None

        # create tmpdirs
        self._executorDict[self._kernelAtom].create_tmpdirs()
        for item in self._addonAtomList:
            self._executorDict[item].create_tmpdirs()

    def dispose(self):
        for item in reversed(self._addonAtomList):
            self._executorDict[item].remove_tmpdirs()
        self._executorDict[self._kernelAtom].remove_tmpdirs()

    def get_progress(self):
        return KernelInstallProgress(self)

    def unpack(self):
        assert self._progress == KernelInstallProgress.STEP_INIT

        self._executorDict[self._kernelAtom].src_unpack()
        for item in self._addonAtomList:
            self._executorDict[item].exec_src_unpack()
        self._progress = KernelInstallProgress.STEP_UNPACKED

    def patch_kernel(self):
        assert self._progress == KernelInstallProgress.STEP_UNPACKED

        for addon_item in self._addonAtomList:
            self._executorDict[addon_item].exec_kernel_addon_patch_kernel(self._kernelAtom)
        self._progress = KernelInstallProgress.STEP_PATCHED

    def generate_kernel_config_file(self):
        assert self._progress == KernelInstallProgress.STEP_PATCHED

        rulesDict = dict()
        workDir = self._executorDict[self._kernelAtom].get_workdir()
        self._kcfgRulesTmpFile = os.path.join(workDir, "config.rules")
        self._dotCfgFile = os.path.join(workDir, ".config")

        # head rules
        if True:
            buf = ""

            # default hostname
            buf += "DEFAULT_HOSTNAME=\"(none)\"\n"
            buf += "\n"

            # deprecated symbol, but many drivers still need it
            buf += "FW_LOADER=y\n"
            buf += "\n"

            # atk9k depends on it
            buf += "DEBUG_FS=y\n"
            buf += "\n"

            # H3C CAS 2.0 still use legacy virtio device, so it is needed
            buf += "VIRTIO_PCI_LEGACY=y\n"
            buf += "\n"

            # we still need iptables
            buf += "NETFILTER_XTABLES=y\n"
            buf += "IP_NF_IPTABLES=y\n"
            buf += "IP_NF_ARPTABLES=y\n"
            buf += "\n"

            # it seems we still need this, why?
            buf += "FB=y\n"
            buf += "DRM_FBDEV_EMULATION=y\n"
            buf += "\n"

            # net-wireless/iwd needs them, FIXME
            buf += "PKCS8_PRIVATE_KEY_PARSER=y\n"
            buf += "KEY_DH_OPERATIONS=y\n"
            buf += "\n"

            # debug feature
            if True:
                # killing CONFIG_VT is failed for now
                buf += "TTY=y\n"
                buf += "[symbols:VT]=y\n"
                buf += "[symbols:/Device Drivers/Graphics support/Console display driver support]=y\n"
                buf += "\n"

            # symbols we dislike
            buf += "[debugging-symbols:/]=n\n"
            buf += "[deprecated-symbols:/]=n\n"
            buf += "[workaround-symbols:/]=n\n"
            buf += "[experimental-symbols:/]=n\n"
            buf += "[dangerous-symbols:/]=n\n"
            buf += "\n"

            rulesDict["head"] = buf

        # build-in rules
        for fn in sorted(pkg_resources.resource_listdir(__name__, "kernel-config-rules")):
            if not fn.endswith(".rules"):
                continue
            m = re.fullmatch(r'([0-9]+-)?(.*)\.rules', fn)
            if m is not None:
                rname = m.group(2)
            rulesDict[rname] = pkg_resources.resource_string(__name__, os.path.join("kernel-config-rules", fn)).decode("iso8859-1")

        # addon rules
        for addon_item in self._addonAtomList:
            buf = self._executorDict[addon_item].exec_kernel_addon_contribute_config_rules()
            rulesDict[addon_item.name] = buf

        # sysadmin rules
        rulesDict["custom"] = ""            # FIXME

        # generate .config file
        with open(self._kcfgRulesTmpFile, "w") as f:
            for name, buf in rulesDict.items():
                f.write("## %s ######################\n" % (name))
                f.write("\n")
                f.write(buf)
                f.write("\n")
                f.write("\n")
                f.write("\n")

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            Util.shellCall("/bin/sed -i '/VT=n/d' %s" % self._kcfgRulesTmpFile)

        # generate the real ".config"
        # FIXME: moved here from a seperate process, leakage?
        pylkcutil.generator.generate(workDir, "allnoconfig+module", self._kcfgRulesTmpFile, output=self._dotCfgFile)

        # "make olddefconfig" may change the .config file further
        with TempChdir(workDir):
            Util.shellCall("make olddefconfig")

        self._progress = KernelInstallProgress.STEP_KERNEL_CONFIG_FILE_GENERATED

    def build(self):
        assert self._progress == KernelInstallProgress.STEP_KERNEL_CONFIG_FILE_GENERATED

        self._executorDict[self._kernelAtom].exec_kernel_build()
        for item in self._addonAtomList:
            self._executorDict[item].exec_kernel_addon_build()
        self._progress = KernelInstallProgress.STEP_KERNEL_BUILT

    def install(self):
        assert self._progress == KernelInstallProgress.STEP_KERNEL_BUILT

        self._executorDict[self._kernelAtom].exec_kernel_install()
        for item in self._addonAtomList:
            self._executorDict[item].exec_kernel_addon_install()
        self._progress = KernelInstallProgress.STEP_KERNEL_INSTALLED

    def retire_old_boot_entries(self):
        assert self._progress == KernelInstallProgress.STEP_KERNEL_INSTALLED

        os.makedirs(self._bbki._fsLayout.get_boot_history_dir(), exist_ok=True)
        for be in BootEntryUtils(self).getBootEntryList():
            if be != self._targetBootEntry:
                for fullfn in BootEntryUtils(self).getBootEntryFilePathList(be):
                    shutil.move(fullfn, self._bbki._fsLayout.get_boot_history_dir())
        self._progress = KernelInstallProgress.STEP_OLD_BOOT_ENTRIES_RETIRED


class KernelInstallProgress:

    STEP_INIT = 1
    STEP_UNPACKED = 2
    STEP_PATCHED = 3
    STEP_KERNEL_CONFIG_FILE_GENERATED = 4
    STEP_KERNEL_BUILT = 5
    STEP_KERNEL_INSTALLED = 5
    STEP_OLD_BOOT_ENTRIES_RETIRED = 5

    def __init__(self, parent):
        self._parent = parent
        self._progress = self.STEP_INIT

    @property
    def progress(self):
        return self._progress

    @property
    def target_boot_dir(self):
        return self._parent._targetBootEntry

    @property
    def kernel_config_filepath(self):
        assert self._parent._dotCfgFile is not None
        return self._parent._dotCfgFile

    @property
    def kernel_config_rules_filepath(self):
        assert self._parent._kcfgRulesTmpFile is not None
        return self._parent._kcfgRulesTmpFile

    @property
    def kernel_source_signature(self):
        # FIXME
        assert False


class BootEntryUtils:

    def __init__(self, bbki):
        self._bbki = bbki

    def getBootEntryList(self, history_entry=False):
        if not history_entry:
            dirpath = self._bbki._fsLayout.get_boot_dir()
        else:
            dirpath = self._bbki._fsLayout.get_boot_history_dir()

        ret = []
        for kernelFile in sorted(os.listdir(dirpath), reverse=True):
            if kernelFile.startswith("kernel-"):
                ret.append(BootEntry.new_from_postfix(self._bbki, kernelFile[len("kernel-"):]))
        return ret

    def getBootEntryFilePathList(self, bootEntry):
        return [
            bootEntry.kernel_filepath,
            bootEntry.kernel_config_filepath,
            bootEntry.kernel_config_rules_filepath,
            bootEntry.initrd_filepath,
            bootEntry.initrd_tar_filepath,
        ]


class BootEntryWrapper:

    def __init__(self, boot_entry):
        self._bootEntry = boot_entry
        self._modulesDir = self._bbki._fsLayout.get_kernel_modules_dir(self._bootEntry.verstr)

    @property
    def modules_dir(self):
        return self._modulesDir

    @property
    def firmware_dir(self):
        return self._bbki._fsLayout.get_firmware_dir()

    @property
    def src_arch(self):
        # FIXME: what's the difference with arch?

        if self._bootEntry.arch == "i386" or self._bootEntry.arch == "x86_64":
            return "x86"
        elif self._bootEntry.arch == "sparc32" or self._bootEntry.arch == "sparc64":
            return "sparc"
        elif self._bootEntry.arch == "sh":
            return "sh64"
        else:
            return self._bootEntry.arch

    def get_kmod_filenames(self, kmod_alias, with_deps=False):
        return [x[len(self._modulesDir):] for x in self.get_kmod_filepaths(kmod_alias, with_deps)]

    def get_kmod_filepaths(self, kmod_alias, with_deps=False):
        kmodList = dict()                                           # use dict to remove duplication while keeping order
        ctx = kmod.Kmod(self._modulesDir.encode("utf-8"))           # FIXME: why encode is neccessary?
        self._getKmodAndDeps(ctx, kmod_alias, with_deps, kmodList)
        return list(kmodList.fromkeys())

    def get_firmware_filenames(self, kmod_filepath):
        return self._getFirmwareImpl(kmod_filepath, True)

    def get_firmware_filepaths(self, kmod_filepath):
        return self._getFirmwareImpl(kmod_filepath, False)

    def _getFirmwareImpl(self, kmodFilePath, bReturnNameOrPath):
        ret = []

        # python-kmod bug: can only recognize the last firmware in modinfo
        # so use the command output of modinfo directly
        for line in Util.cmdCall("/bin/modinfo", kmodFilePath).split("\n"):
            m = re.fullmatch("firmware: +(\\S.*)", line)
            if m is not None:
                if bReturnNameOrPath:
                    ret.append(m.group(1))
                else:
                    ret.append(os.path.join(self._bbki._fsLayout.get_firmware_dir(), m.group(1)))

        # add standard files
        standardFiles = [
            ".ctime",
            "regulatory.db",
            "regulatory.db.p7s",
        ]
        if bReturnNameOrPath:
            ret += standardFiles
        else:
            ret += [os.path.join(self._bbki._fsLayout.get_firmware_dir(), x) for x in standardFiles]

        # return value
        return ret

    def _getKmodAndDeps(self, ctx, kmodAlias, withDeps, result):
        kmodObjList = list(ctx.lookup(kmodAlias))
        if len(kmodObjList) > 0:
            assert len(kmodObjList) == 1
            kmodObj = kmodObjList[0]

            if withDeps and "depends" in kmodObj.info and kmodObj.info["depends"] != "":
                for kmodAlias in kmodObj.info["depends"].split(","):
                    self._getKmodAndDeps(ctx, kmodAlias, result)

            if kmodObj.path is not None:
                # this module is not built into the kernel
                result[kmodObj.path] = None
