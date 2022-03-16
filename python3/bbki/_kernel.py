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
import platform
import pylkcutil
import pkg_resources
import robust_layer.simple_fops
from ._util import Util
from ._boot_entry import BootEntry
from ._boot_entry import BootEntryWrapper
from ._repo_atom_exec import BbkiAtomExecutor
from ._exception import KernelInstallError


def Step(progress_step):
    def decorator(func):
        def wrapper(self):
            assert self._progress == progress_step
            func(self)
            self._progress += 1
        return wrapper
    return decorator


class KernelInstallProgress:

    STEP_INIT = 1
    STEP_UNPACKED = 2
    STEP_PATCHED = 3
    STEP_KERNEL_CONFIG_FILE_GENERATED = 4
    STEP_KERNEL_INSTALLED = 5

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


class KernelInstaller:

    def __init__(self, bbki, kernel_atom, kernel_atom_item_list, initramfs_atom):
        self._bbki = bbki

        self._kernelAtom = kernel_atom
        self._addonAtomList = kernel_atom_item_list
        self._initramfsAtom = initramfs_atom

        self._executorDict = dict()
        self._executorDict[kernel_atom] = BbkiAtomExecutor(self._bbki, kernel_atom)
        for item in kernel_atom_item_list:
            self._executorDict[item] = BbkiAtomExecutor(self._bbki, item)
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom] = BbkiAtomExecutor(self._bbki, self._initramfsAtom)

        self._progress = KernelInstallProgress.STEP_INIT
        self._targetBootEntry = None

        self._myTmpDir = os.path.join(self._bbki.config.tmp_dir, "kernel")
        self._kcfgRulesTmpFile = os.path.join(self._myTmpDir, "config.rules")
        self._dotCfgFile = os.path.join(self._myTmpDir, "config")

        # create tmpdirs
        robust_layer.simple_fops.mk_empty_dir(self._myTmpDir)
        self._executorDict[self._kernelAtom].create_tmpdirs()
        for item in self._addonAtomList:
            self._executorDict[item].create_tmpdirs()
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom].create_tmpdirs()

    def get_progress(self):
        return KernelInstallProgress(self)

    @Step(KernelInstallProgress.STEP_INIT)
    def unpack(self):
        self._executorDict[self._kernelAtom].exec_src_unpack()
        for item in self._addonAtomList:
            self._executorDict[item].exec_src_unpack()
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom].exec_src_unpack()

        self._targetBootEntry = BootEntry(self._bbki, platform.machine(), _getKernelVerStr((self._executorDict[self._kernelAtom].get_work_dir())))

    @Step(KernelInstallProgress.STEP_UNPACKED)
    def patch_kernel(self):
        for addon_item in self._addonAtomList:
            self._executorDict[addon_item].exec_kernel_addon_patch_kernel(self._kernelAtom, self._targetBootEntry)

    @Step(KernelInstallProgress.STEP_PATCHED)
    def generate_kernel_config_file(self):
        rulesDict = dict()

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
            rulesDict[addon_item.name] = self._executorDict[addon_item].exec_kernel_addon_contribute_config_rules(self._kernelAtom, self._targetBootEntry)

        # initramfs rules
        if self._initramfsAtom is not None:
            rulesDict["initramfs"] = self._executorDict[self._initramfsAtom].exec_initramfs_contribute_config_rules(self._kernelAtom, self._targetBootEntry)

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
        pylkcutil.generator.generate(self._executorDict[self._kernelAtom].get_work_dir(),
                                     "allnoconfig+module",
                                     self._kcfgRulesTmpFile, output=self._dotCfgFile)

    @Step(KernelInstallProgress.STEP_KERNEL_CONFIG_FILE_GENERATED)
    def install(self):
        self._executorDict[self._kernelAtom].exec_kernel_install(self._dotCfgFile, self._kcfgRulesTmpFile, self._targetBootEntry)
        for item in self._addonAtomList:
            self._executorDict[item].exec_kernel_addon_install(self._kernelAtom, self._targetBootEntry)

        for be in self._bbki.get_boot_entries():
            if be != self._targetBootEntry:
                BootEntryWrapper(be).move_to_history()

        self._executorDict[self._kernelAtom].exec_kernel_cleanup(self._targetBootEntry)
        for item in self._addonAtomList:
            self._executorDict[item].exec_kernel_addon_cleanup()

    def dispose(self):
        if self._initramfsAtom is not None:
            self._executorDict[self._initramfsAtom].remove_tmpdirs()
        for item in reversed(self._addonAtomList):
            self._executorDict[item].remove_tmpdirs()
        self._executorDict[self._kernelAtom].remove_tmpdirs()
        robust_layer.simple_fops.rm(self._myTmpDir)


def _getKernelVerStr(kernelDir):
    version = None
    patchlevel = None
    sublevel = None
    extraversion = None
    with open(os.path.join(kernelDir, "Makefile")) as f:
        buf = f.read()

        m = re.search("VERSION = ([0-9]+)", buf, re.M)
        if m is None:
            raise KernelInstallError("illegal kernel source directory")
        version = int(m.group(1))

        m = re.search("PATCHLEVEL = ([0-9]+)", buf, re.M)
        if m is None:
            raise KernelInstallError("illegal kernel source directory")
        patchlevel = int(m.group(1))

        m = re.search("SUBLEVEL = ([0-9]+)", buf, re.M)
        if m is None:
            raise KernelInstallError("illegal kernel source directory")
        sublevel = int(m.group(1))

        m = re.search("EXTRAVERSION = (\\S+)", buf, re.M)
        if m is not None:
            extraversion = m.group(1)

    if extraversion is not None:
        return "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
    else:
        return "%d.%d.%d" % (version, patchlevel, sublevel)
