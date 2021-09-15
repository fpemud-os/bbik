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
import pkg_resources
import robust_layer.simple_fops
from ._util import Util
from ._util import TempChdir
from ._boot_entry import BootEntry
from ._boot_entry import BootEntryUtils
from ._boot_entry import BootEntryWrapper
from ._repo import BbkiAtomExecutor


class KernelInstaller:

    def __init__(self, bbki, kernel_atom, kernel_atom_item_list, initramfs_atom):
        self._bbki = bbki

        self._kernelAtom = kernel_atom
        self._addonAtomList = kernel_atom_item_list
        self._initramfsAtom = initramfs_atom

        self._executorDict = dict()
        self._executorDict[kernel_atom] = BbkiAtomExecutor(kernel_atom)
        for item in kernel_atom_item_list:
            self._executorDict[item] = BbkiAtomExecutor(item)
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom] = BbkiAtomExecutor(self._initramfsAtom)

        self._progress = KernelInstallProgress.STEP_INIT
        self._targetBootEntry = BootEntry(self._bbki, os.uname().machine, self._kernelAtom.verstr)

        self._kcfgRulesTmpFile = None
        self._dotCfgFile = None

        # create tmpdirs
        self._executorDict[self._kernelAtom].create_tmpdirs()
        for item in self._addonAtomList:
            self._executorDict[item].create_tmpdirs()
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom].create_tmpdirs()

    def dispose(self):
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom].remove_tmpdirs()
        for item in reversed(self._addonAtomList):
            self._executorDict[item].remove_tmpdirs()
        self._executorDict[self._kernelAtom].remove_tmpdirs()

    def get_progress(self):
        return KernelInstallProgress(self)

    def unpack(self):
        assert self._progress == KernelInstallProgress.STEP_INIT

        self._executorDict[self._kernelAtom].exec_src_unpack()
        for item in self._addonAtomList:
            self._executorDict[item].exec_src_unpack()
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom].exec_src_unpack()
        self._progress = KernelInstallProgress.STEP_UNPACKED

    def patch_kernel(self):
        assert self._progress == KernelInstallProgress.STEP_UNPACKED

        for addon_item in self._addonAtomList:
            self._executorDict[addon_item].exec_kernel_addon_patch_kernel(self._kernelAtom)
        self._progress = KernelInstallProgress.STEP_PATCHED

    def generate_kernel_config_file(self):
        assert self._progress == KernelInstallProgress.STEP_PATCHED

        rulesDict = dict()
        workDir = self._executorDict[self._kernelAtom].get_work_dir()
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
            rulesDict[addon_item.name] = self._executorDict[addon_item].exec_kernel_addon_contribute_config_rules(self._kernelAtom)

        # initramfs rules
        if self._initramfsAtom is not None:
            rulesDict["initramfs"] = self._executorDict[self._initramfsAtom].exec_initramfs_contribute_config_rules(self._kernelAtom)

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
            self._executorDict[item].exec_kernel_addon_build(self._kernelAtom)
        self._progress = KernelInstallProgress.STEP_KERNEL_BUILT

    def install(self):
        assert self._progress == KernelInstallProgress.STEP_KERNEL_BUILT

        with self._bbki._bootDirWriter:
            self._executorDict[self._kernelAtom].exec_kernel_install()
            for item in self._addonAtomList:
                self._executorDict[item].exec_kernel_addon_install(self._kernelAtom)

            for be in BootEntryUtils(self._bbki).getBootEntryList():
                if be != self._targetBootEntry:
                    BootEntryWrapper(be).move_to_history()

        self._progress = KernelInstallProgress.STEP_KERNEL_INSTALLED


class KernelInstallProgress:

    STEP_INIT = 1
    STEP_UNPACKED = 2
    STEP_PATCHED = 3
    STEP_KERNEL_CONFIG_FILE_GENERATED = 4
    STEP_KERNEL_BUILT = 5
    STEP_KERNEL_INSTALLED = 6

    def __init__(self, parent):
        self._parent = parent
        self._progress = self.STEP_INIT

    @property
    def progress(self):
        return self._progress

    @property
    def target_boot_entry(self):
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
