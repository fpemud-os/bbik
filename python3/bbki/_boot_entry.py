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
import glob
from ._util import Util


class BootEntry:

    def __init__(self, bbki, arch, verstr, history_entry=False):
        self._bbki = bbki
        self._arch = arch
        self._verstr = verstr
        if not history_entry:
            self._bootDir = self._bbki._fsLayout.get_boot_dir()
        else:
            self._bootDir = self._bbki._fsLayout.get_boot_history_dir()

    @property
    def postfix(self):
        # string, eg: "x86_64-3.9.11-gentoo-r1"
        return self._arch + "-" + self._verstr

    @property
    def arch(self):
        # string, eg: "x86_64"
        return self._arch

    @property
    def verstr(self):
        # string, eg: "3.9.11-gentoo-r1"
        return self._verstr

    @property
    def ver(self):
        # string, eg: "3.9.11"
        try:
            return self._verstr[:self._verstr.index("-")]
        except ValueError:
            return self._verstr

    @property
    def kernel_filename(self):
        # string, eg: "kernel-x86_64-3.9.11-gentoo-r1"
        return "kernel-" + self.postfix

    @property
    def kernel_filepath(self):
        # string, eg: "/boot/kernel-x86_64-3.9.11-gentoo-r1"
        return os.path.join(self._bootDir, self.kernel_filename)

    @property
    def kernel_config_filename(self):
        # string, eg: "config-x86_64-3.9.11-gentoo-r1"
        return "config-" + self.postfix

    @property
    def kernel_config_filepath(self):
        # string, eg: "/boot/config-x86_64-3.9.11-gentoo-r1"
        return os.path.join(self._bootDir, self.kernel_config_filename)

    @property
    def kernel_config_rules_filename(self):
        # string, eg: "config-x86_64-3.9.11-gentoo-r1.rules"
        return "config-" + self.postfix + ".rules"

    @property
    def kernel_config_rules_filepath(self):
        # string, eg: "/boot/config-x86_64-3.9.11-gentoo-r1.rules"
        return os.path.join(self._bootDir, self.kernel_config_rules_filename)

    @property
    def kernel_modules_dirpath(self):
        # string, eg: "/lib/modules/5.1.14-gentoo-r1"
        return self._bbki._fsLayout.get_kernel_modules_dir(self._verstr)

    @property
    def initrd_filename(self):
        # string, eg: "initramfs-x86_64-3.9.11-gentoo-r1"
        return "initramfs-" + self.postfix

    @property
    def initrd_filepath(self):
        # string, eg: "/boot/initramfs-x86_64-3.9.11-gentoo-r1"
        return os.path.join(self._bootDir, self.initrd_filename)

    @property
    def initrd_tar_filename(self):
        # string, eg: "initramfs-files-x86_64-3.9.11-gentoo-r1.tar.bz2"
        return "initramfs-files-" + self.postfix + ".tar.bz2"

    @property
    def initrd_tar_filepath(self):
        # string, eg: "/boot/initramfs-x86_64-3.9.11-gentoo-r1.tar.bz2"
        return os.path.join(self._bootDir, self.initrd_tar_filename)

    def is_historical(self):
        return (self._bootDir == self._bbki._fsLayout.get_boot_history_dir())

    def has_kernel_files(self):
        if not os.path.exists(self.kernel_filepath):
            return False
        if not os.path.exists(self.kernel_config_filepath):
            return False
        if not os.path.exists(self.kernel_config_rules_filepath):
            return False
        if not os.path.exists(self._bbki._fsLayout.get_kernel_modules_dir(self._verstr)):
            return False
        if not os.path.exists(self._bbki._fsLayout.get_firmware_dir()):
            return False
        return True

    def has_initrd_files(self):
        if not os.path.exists(self.initrd_filepath):
            return False
        if not os.path.exists(self.initrd_tar_filepath):
            return False
        return True

    def has_kernel_modules_dir(self):
        if not os.path.exists(self.kernel_modules_dirpath):
            return False
        return True

    def __eq__(self, other):
        return type(self) == type(other) and self._bbki == other._bbki and \
               self._arch == other._arch and self._verstr == other._verstr and \
               self._bootDir == other._bootDir


class BootEntryWrapper:

    def __init__(self, boot_entry):
        self._bbki = boot_entry._bbki
        self._bootEntry = boot_entry
        self._modulesDir = self._bbki._fsLayout.get_kernel_modules_dir(self._bootEntry.verstr)

    @property
    def kernel_modules_dir(self):
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

    def get_filepaths(self, exists_only=False):
        ret = [
            self._bootEntry.kernel_filepath,
            self._bootEntry.kernel_config_filepath,
            self._bootEntry.kernel_config_rules_filepath,
            self._bootEntry.initrd_filepath,
            self._bootEntry.initrd_tar_filepath,
        ]
        if exists_only:
            ret = [x for x in ret if os.path.exists(x)]
        return ret

    def get_kmod_filenames_by_alias(self, kmod_alias, with_deps=False):
        return [x[len(self._modulesDir):] for x in self.get_kmod_filepaths_by_alias(kmod_alias, with_deps)]

    def get_kmod_filepaths_by_alias(self, kmod_alias, with_deps=False):
        kmodList = dict()                                           # use dict to remove duplication while keeping order
        ctx = kmod.Kmod(self._modulesDir.encode("utf-8"))           # FIXME: why encode is neccessary?
        self._getKmodAndDeps(ctx, kmod_alias, with_deps, kmodList)
        return list(kmodList)

    def get_firmware_filenames_by_kmod(self, kmod_filepath):
        # python-kmod bug: can only recognize the last firmware in modinfo
        # so use the command output of modinfo directly
        ret = []
        for line in Util.cmdCall("/bin/modinfo", kmod_filepath).split("\n"):
            m = re.fullmatch("firmware: +(\\S.*)", line)
            if m is not None:
                ret.append(m.group(1))
        return ret

    def get_firmware_filepaths_by_kmod(self, kmod_filepath):
        return [os.path.join(self._bbki._fsLayout.get_firmware_dir(), x) for x in self.get_firmware_filenames_by_kmod(kmod_filepath)]

    def get_firmware_filenames(self):
        ret = set()
        for fullKoFn in glob.glob(os.path.join(self._modulesDir, "**", "*.ko"), recursive=True):
            ret |= set(self.get_firmware_filenames_by_kmod(fullKoFn))
        ret |= set([
            ".ctime",
            "regulatory.db",
            "regulatory.db.p7s",
        ])
        return sorted(list(ret))

    def get_firmware_filepaths(self):
        return [os.path.join(self._bbki._fsLayout.get_firmware_dir(), x) for x in self.get_firmware_filenames()]

    def _getKmodAndDeps(self, ctx, kmodAlias, withDeps, result):
        kmodObjList = list(ctx.lookup(kmodAlias))
        if len(kmodObjList) > 0:
            assert len(kmodObjList) == 1
            kmodObj = kmodObjList[0]

            if withDeps and "depends" in kmodObj.info and kmodObj.info["depends"] != "":
                for kmodAlias in kmodObj.info["depends"].split(","):
                    self._getKmodAndDeps(ctx, kmodAlias, withDeps, result)

            if kmodObj.path is not None:
                # this module is not built into the kernel
                result[kmodObj.path] = None


class BootEntryUtils:

    def __init__(self, bbki):
        self._bbki = bbki

    def new_from_postfix(self, postfix, history_entry=False):
        # postfix example: x86_64-3.9.11-gentoo-r1
        partList = postfix.split("-")
        if len(partList) < 2:
            raise ValueError("illegal postfix")
        if not Util.isValidKernelArch(partList[0]):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal postfix")
        if not Util.isValidKernelVer(partList[1]):          # FIXME: isValidKernelVer should be moved out from util
            raise ValueError("illegal postfix")

        arch = partList[0]
        verstr = "-".join(partList[1:])
        return BootEntry(self._bbki, arch, verstr, history_entry)

    def getBootEntryList(self, history_entry=False):
        if not history_entry:
            dirpath = self._bbki._fsLayout.get_boot_dir()
        else:
            dirpath = self._bbki._fsLayout.get_boot_history_dir()

        ret = []
        for kernelFile in sorted(os.listdir(dirpath), reverse=True):
            if kernelFile.startswith("kernel-"):
                ret.append(self.new_from_postfix(kernelFile[len("kernel-"):], history_entry))
        return ret

    def getRedundantKernelModulesDirs(self, bootEntryList):
        if not os.path.exists(self._bbki._fsLayout.get_kernel_modules_dir()):
            return []

        ret = glob.glob(os.path.join(self._bbki._fsLayout.get_kernel_modules_dir(), "*"))  # mark /lib/modules/* (no recursion) as to-be-deleted
        for be in bootEntryList:
            try:
                ret.remove(self._bbki._fsLayout.get_kernel_modules_dir(be.verstr))         # don't delete files belongs to a boot-entry
            except ValueError:
                pass
        return ret

    def getRedundantFirmwareFiles(self, bootEntryList):
        if not os.path.exists(self._bbki._fsLayout.get_firmware_dir()):
            return []

        tset = set(Util.globDirRecursively(self._bbki._fsLayout.get_firmware_dir()))   # mark /lib/firmware/* (recursive) as to-be-deleted
        for be in bootEntryList:
            for fp in BootEntryWrapper(be).get_firmware_filepaths():
                while fp != "/":
                    tset.discard(fp)
                    fp = os.path.dirname(fp)                                           # don't delete files (and it ancestor directories) belongs to a boot-entry
        return sorted(list(tset))
