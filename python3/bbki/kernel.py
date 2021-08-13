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
import pylkcutil
import robust_layer.simple_fops
from .util import Util
from .util import TempChdir
from .repo import BbkiFileExecutor


class KernelInfo:

    def __init__(self):
        self._arch = None
        self._verstr = None

    @property
    def name(self):
        # string, eg: "linux-x86_64-3.9.11-gentoo-r1"
        return "linux-" + self._arch + "-" + self._verstr

    @property
    def postfix(self):
        # string, eg: "x86_64-3.9.11-gentoo-r1"
        return self._arch + "-" + self._verstr

    @property
    def arch(self):
        # string, eg: "x86_64".
        return self._arch

    @property
    def src_arch(self):
        # FIXME: what's the difference with arch?

        if self._arch == "i386" or self._arch == "x86_64":
            return "x86"
        elif self._arch == "sparc32" or self._arch == "sparc64":
            return "sparc"
        elif self._arch == "sh":
            return "sh64"
        else:
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

    def ___eq___(self, other):
        return self._arch == other._arch and self._verstr == other._verstr

    @staticmethod
    def new_from_postfix(postfix):
        # postfix example: x86_64-3.9.11-gentoo-r1
        partList = postfix.split("-")
        if len(partList) < 2:
            raise ValueError("illegal postfix")
        if not Util.isValidKernelArch(partList[0]):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal postfix")
        if not Util.isValidKernelVer(partList[1]):          # FIXME: isValidKernelVer should be moved out from util
            raise ValueError("illegal postfix")

        ret = KernelInfo()
        ret._arch = partList[0]
        ret._verstr = "-".join(partList[1:])
        return ret

    @staticmethod
    def new_from_verstr(arch, verstr):
        if arch == "native":
            arch = os.uname().machine
        if not Util.isValidKernelArch(arch):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal arch")

        # verstr example: 3.9.11-gentoo-r1
        partList = verstr.split("-")
        if len(partList) < 1:
            raise ValueError("illegal verstr")
        if not Util.isValidKernelVer(partList[0]):          # FIXME: isValidKernelVer should be moved out from util
            raise ValueError("illegal verstr")

        ret = KernelInfo()
        ret._arch = arch
        ret._verstr = verstr
        return ret

    @staticmethod
    def new_from_kernel_srcdir(arch, kernel_srcdir):
        if arch == "native":
            arch = os.uname().machine
        if not Util.isValidKernelArch(arch):         # FIXME: isValidKernelArch should be moved out from util
            raise ValueError("illegal arch")

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

        ret = KernelInfo()
        ret._arch = arch
        if extraversion is not None:
            ret._verstr = "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
        else:
            ret._verstr = "%d.%d.%d" % (version, patchlevel, sublevel)
        return ret


class Kernel:

    def __init__(self, bbki, kernel_verstr):
        self._bbki = bbki
        self._verstr = kernel_verstr
        self._modulesDir = self._bbki._fsLayout.get_kernel_modules_dir(self._verstr)

    def exists(self):
        BootEntry()


    def get_kernel_module_filenames(self, kmod_alias):
        return [x[len(self._modulesDir):] for x in self.get_kernel_module_filepaths(kmod_alias)]

    def get_kernel_module_filepaths(self, kmod_alias):
        kmodList = dict()                                     # use dict to remove duplication while keeping order
        ctx = kmod.Kmod(self._modulesDir.encode("utf-8"))     # FIXME: why encode is neccessary?
        self._getKmodAndDeps(ctx, kmod_alias, kmodList)
        return list(kmodList.fromkeys())

    def _getKmodAndDeps(self, ctx, kmodAlias, result):
        kmodObjList = list(ctx.lookup(kmodAlias))
        if len(kmodObjList) > 0:
            assert len(kmodObjList) == 1
            kmodObj = kmodObjList[0]

            if "depends" in kmodObj.info and kmodObj.info["depends"] != "":
                for kmodAlias in kmodObj.info["depends"].split(","):
                    self._getKmodAndDeps(ctx, kmodAlias, result)

            if kmodObj.path is not None:
                # this module is not built into the kernel
                result[kmodObj.path] = None


class KernelInstaller:

    def __init__(self, bbki, kernel_item, kernel_addon_item_list):
        self._bbki = bbki

        self._kernelItem = kernel_item
        self._addonItemList = kernel_addon_item_list

        self._executorDict = dict()
        self._executorDict[kernel_item] = BbkiFileExecutor(kernel_item)
        for item in kernel_addon_item_list:
            self._executorDict[item] = BbkiFileExecutor(item)

        # create tmpdirs
        self._executorDict[self._kernelItem].create_tmpdirs()
        for item in self._addonItemList:
            self._executorDict[item].create_tmpdirs()

    def dispose(self):
        for item in reversed(self._addonItemList):
            self._executorDict[item].remove_tmpdirs()
        self._executorDict[self._kernelItem].remove_tmpdirs()

    def get_build_target(self):
        return KernelInfo.new_from_verstr("amd64", self._kernelItem.verstr)

    def unpack(self):
        self._executorDict[self._kernelItem].src_unpack()
        for item in self._addonItemList:
            self._executorDict[item].exec_src_unpack()

    def patch_kernel(self):
        for addon_item in self._addonItemList:
            self._executorDict[addon_item].exec_kernel_addon_patch_kernel(self._kernelItem)

    def generate_kernel_dotcfg(self):
        rulesDict = dict()
        workDir = self._executorDict[self._kernelItem].get_workdir()
        kcfgRulesTmpFile = os.path.join(workDir, "config.rules")
        dotCfgFile = os.path.join(workDir, ".config")

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

        # addon rules
        for addon_item in self._addonItemList:
            buf = self._executorDict[addon_item].exec_kernel_addon_contribute_config_rules()
            rulesDict[addon_item.name] = buf

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            Util.shellCall("/bin/sed -i '/VT=n/d' %s" % (kcfgRulesTmpFile))

        # generate the real ".config"
        # FIXME: moved here from a seperate process, leakage?
        pylkcutil.generator.generate(workDir, "allnoconfig+module", kcfgRulesTmpFile, output=dotCfgFile)

        # "make olddefconfig" may change the .config file further
        with TempChdir(workDir):
            Util.shellCall("make olddefconfig")

    def build(self):
        self._executorDict[self._kernelItem].exec_kernel_build()
        for item in self._addonItemList:
            self._executorDict[item].exec_kernel_addon_build()

    def install(self):
        self._executorDict[self._kernelItem].exec_kernel_install()
        for item in self._addonItemList:
            self._executorDict[item].exec_kernel_addon_install()
