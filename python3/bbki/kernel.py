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
import robust_layer.simple_fops
from .util import Util
from .util import TempChdir
from .repo import BbkiFileExecutor


class KernelBuildTarget:

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

        ret = KernelBuildTarget()
        ret._arch = partList[0]
        ret._verstr = "-".join(partList[1:])
        return ret

    @staticmethod
    def new_from_verstr(arch, verstr):
        # verstr example: 3.9.11-gentoo-r1
        partList = verstr.split("-")
        if len(partList) < 1:
            raise ValueError("illegal verstr")
        if not Util.isValidKernelVer(partList[0]):          # FIXME: isValidKernelVer should be moved out from util
            raise ValueError("illegal verstr")

        ret = KernelBuildTarget()
        ret._arch = arch
        ret._verstr = verstr
        return ret

    @staticmethod
    def new_from_kernel_srcdir(arch, kernel_srcdir):
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

        ret = KernelBuildTarget()
        ret._arch = arch
        if extraversion is not None:
            ret._verstr = "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
        else:
            ret._verstr = "%d.%d.%d" % (version, patchlevel, sublevel)
        return ret


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
        return KernelBuildTarget.new_from_verstr("amd64", self._kernelItem.verstr)

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

        # generate rules file
        _generateKernelCfgRulesFile(kcfgRulesTmpFile, rulesDict)

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            Util.shellCall("/bin/sed -i '/VT=n/d' %s" % (kcfgRulesTmpFile))

        # generate the real ".config"
        # FIXME
        Util.cmdCall("/usr/libexec/fpemud-os-sysman/bugfix-generate-dotcfgfile.py", workDir, kcfgRulesTmpFile, dotCfgFile)

        # "make olddefconfig" may change the .config file further
        with TempChdir(workDir):
            Util.shellCall("/usr/bin/make olddefconfig")

    def build(self):
        self._executorDict[self._kernelItem].exec_kernel_build()
        for item in self._addonItemList:
            self._executorDict[item].exec_kernel_addon_build()

    def install(self):
        self._executorDict[self._kernelItem].exec_kernel_install()
        for item in self._addonItemList:
            self._executorDict[item].exec_kernel_addon_install()


class KernelCleaner:

    def __init__(self):
        pass

    def get_files(self):



        if os.path.exists(self.historyDir):
            ret = []
            for fn in os.listdir(self.historyDir):
                ret.append(os.path.join(self.historyDir, fn))
            return ret
        else:
            return []


def _generateKernelCfgRulesFile(filename, *kargs):
    with open(filename, "w") as f:
        for kcfgRulesMap in kargs:
            for name, buf in kcfgRulesMap.items():
                f.write("## %s ######################\n" % (name))
                f.write("\n")
                f.write(buf)
                f.write("\n")
                f.write("\n")
                f.write("\n")











# get file list to be removed in boot directory
bootFileList = sorted(FkmBootDir().getHistoryFileList())

# get file list to be removed in kernel module directory
moduleFileList = []
if True:
    moduleFileList = os.listdir(kernelModuleDir)
    ret = FkmBootEntry.findCurrent()
    if ret is not None:
        moduleFileList.remove(ret.buildTarget.verstr)
    moduleFileList = sorted([os.path.join(kernelModuleDir, f) for f in moduleFileList])

# get file list to be removed in firmware directory
firmwareFileList = []
if os.path.exists(firmwareDir):
    validList = []
    for ver in os.listdir(kernelModuleDir):
        if ver in moduleFileList:
            continue
        verDir = os.path.join(kernelModuleDir, ver)
        for fullfn in glob.glob(os.path.join(verDir, "**", "*.ko"), recursive=True):
            # python-kmod bug: can only recognize the last firmware in modinfo
            # so use the command output of modinfo directly
            for line in FmUtil.cmdCall("/bin/modinfo", fullfn).split("\n"):
                m = re.fullmatch("firmware: +(\\S.*)", line)
                if m is None:
                    continue
                firmwareName = m.group(1)
                if not os.path.exists(os.path.join(firmwareDir, firmwareName)):
                    continue
                validList.append(firmwareName)

    standardFiles = [
        ".ctime",
        "regulatory.db",
        "regulatory.db.p7s",
    ]
    for root, dirs, files in os.walk(firmwareDir):
        for filepath in files:
            firmwareName = os.path.join(re.sub("^/lib/firmware/?", "", root), filepath)
            if firmwareName in standardFiles:
                continue
            if firmwareName in validList:
                continue
            firmwareFileList.append(firmwareName)

# show file list to be removed in boot directory
print("            Items to be removed in \"/boot\":")
if len(bootFileList) == 0:
    print("              None")
else:
    for f in bootFileList:
        print("              %s" % (f))

# show file list to be removed in kernel module directory
print("            Items to be removed in \"%s\":" % (kernelModuleDir))
if len(moduleFileList) == 0:
    print("              None")
else:
    for f in moduleFileList:
        assert os.path.isdir(os.path.join(kernelModuleDir, f))
        print("              %s/" % (f))

# show file list to be removed in firmware directory
print("            Items to be removed in \"%s\":" % (firmwareDir))
if len(firmwareFileList) == 0:
    print("              None")
else:
    for f in firmwareFileList:
        print("              %s" % (f))

# remove files
if len(bootFileList) > 0 or len(moduleFileList) > 0 or len(firmwareFileList) > 0:
    ret = 1
    print("        - Deleting...")
    for f in bootFileList:
        robust_layer.simple_fops.rm(os.path.join(bootDir, f))
    for f in moduleFileList:
        robust_layer.simple_fops.rm(os.path.join(kernelModuleDir, f))
    for f in firmwareFileList:
        fullfn = os.path.join(firmwareDir, f)
        robust_layer.simple_fops.rm(os.path.join(firmwareDir, f))
        d = os.path.dirname(fullfn)
        if len(os.listdir(d)) == 0:
            os.rmdir(d)
else:
    ret = 0

