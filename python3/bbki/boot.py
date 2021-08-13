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
import pathlib
import robust_layer.simple_fops
from .util import Util
from .kernel import KernelInfo


class BootEntry:

    def __init__(self, bbki, kernel_info, history_entry=False):
        self._bbki = bbki
        self._kernelInfo = kernel_info
        if not history_entry:
            self._bootDir = self._bbki._fsLayout.get_boot_dir()
        else:
            self._bootDir = self._bbki._fsLayout.get_boot_history_dir()

    @property
    def arch(self):
        return self._kernelInfo.arch

    @property
    def kernel_ver(self):
        return self._kernelInfo.ver

    @property
    def kernel_verstr(self):
        return self._kernelInfo.verstr

    @property
    def kernel_filename(self):
        return "kernel-" + self._kernelInfo.postfix

    @property
    def kernel_filepath(self):
        return os.path.join(self._bootDir, self.kernel_filename)

    @property
    def kernel_config_filename(self):
        return "config-"+ self._kernelInfo.postfix

    @property
    def kernel_config_filepath(self):
        return os.path.join(self._bootDir, self.kernel_config_filename)

    @property
    def kernel_config_rules_filename(self):
        return "config-" + self._kernelInfo.postfix + ".rules"

    @property
    def kernel_config_rules_filepath(self):
        return os.path.join(self._bootDir, self.kernel_config_rules_filename)

    @property
    def initrd_filename(self):
        return "initramfs-" + self._kernelInfo.postfix

    @property
    def initrd_filepath(self):
        return os.path.join(self._bootDir, self.initrd_filename)

    @property
    def initrd_tar_filename(self):
        return "initramfs-files-" + self._kernelInfo.postfix + ".tar.bz2"

    @property
    def initrd_tar_filepath(self):
        return os.path.join(self._bootDir, self.initrd_tar_filename)

    def has_kernel_files(self):
        if not os.path.exists(self.kernel_filepath):
            return False
        if not os.path.exists(self.kernel_config_filepath):
            return False
        if not os.path.exists(self.kernel_config_rules_filepath):
            return False
        return True

    def has_initrd_files(self):
        if not os.path.exists(self.initrd_filepath):
            return False
        if not os.path.exists(self.initrd_tar_filepath):
            return False
        return True

    def ___eq___(self, other):
        return self._bbki == other._bbki and self._kernelInfo == other._kernelInfo and self._bootDir == other._bootDir


class BootLoaderGrub:

    def __init__(self, bbki):
        self._bbki = bbki
        self._grubCfgFile = os.path.join(self._bbki._fsLayout.get_grub_dir(), "grub.cfg")

    def getCurrentBootEntry(self):
        if not os.path.exists(self._grubCfgFile):
            return None

        buf = pathlib.Path(self._grubCfgFile).read_text()
        m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*\n  linux \S*/kernel-(\S+) .*\n}', buf)
        if m is not None:
            return BootEntry(KernelInfo.new_from_postfix(m.group(1)))
        else:
            return None

    def uefi_install(self, grubExtraWaitTime, storageLayout, kernelInitCmd):
        grubKernelOpt = "console=ttynull"       # only use console when debug boot process

        # remove old directory
        self.uefi_remove()

        # install /boot/grub and /boot/EFI directory
        # install grub into ESP
        # *NO* UEFI firmware variable is touched, so that we are portable
        Util.cmdCall("grub-install", "--removable", "--target=x86_64-efi", "--efi-directory=%s" % (self._bbki._fsLayout.get_boot_dir()), "--no-nvram")

        # generate grub.cfg
        self._genGrubCfg(storageLayout,
                         ret.buildTarget,
                         grubKernelOpt,
                         grubExtraWaitTime,
                         FmConst.kernelInitCmd)

    def uefi_remove(self):
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "EFI"))
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "grub"))

    def bios_install(self, hwInfo, storageLayout, kernelInitCmd):
        ret = FkmBootEntry.findCurrent()
        if ret is None:
            raise Exception("Invalid current boot item, strange?!")

        grubKernelOpt = "console=ttynull"       # only use console when debug boot process

        # backup old directory
        if os.path.exists("/boot/grub"):
            os.makedirs(self._bbki._fsLayout.get_boot_history_dir(), exist_ok=True)
            robust_layer.simple_fops.mv("/boot/grub", os.path.join(self._bbki._fsLayout.get_boot_history_dir(), "grub"))

        # install /boot/grub directory
        # install grub into disk MBR
        FmUtil.cmdCall("/usr/sbin/grub-install", "--target=i386-pc", storageLayout.get_boot_disk())

        # generate grub.cfg
        self._genGrubCfg(storageLayout,
                         ret.buildTarget,
                         grubKernelOpt,
                         hwInfo.grubExtraWaitTime,
                         FmConst.kernelInitCmd)

    def bios_remove(self, storageLayout):
        # remove MBR
        with open(storageLayout.get_boot_disk(), "wb+") as f:
            f.write(FmUtil.newBuffer(0, 440))

        # remove /boot/grub directory
        robust_layer.simple_fops.rm("/boot/grub")

    def update(self):
        grubcfg = "/boot/grub/grub.cfg"

        lineList = []
        with open(grubcfg) as f:
            lineList = f.read().split("\n")

        lineList2 = []
        b = False
        for line in lineList:
            if not b and re.search("^\\s*menuentry\\s+\\\"History:", line, re.I) is not None:
                b = True
                continue
            if b and re.search("^\\s*}\\s*$", line, re.I) is not None:
                b = False
                continue
            if b:
                continue
            lineList2.append(line)

        with open(grubcfg, "w") as f:
            for line in lineList2:
                f.write(line + "\n")

    def _genGrubCfg(self, boot_mode, grubRootDev, buildTarget, grubKernelOpt, extraTimeout, initCmdline):
        buf = ''
        if boot_mode == Bbki.BOOT_MODE_EFI:
            grubRootDev = layout.get_esp()
            prefix = "/"
        elif boot_mode == Bbki.BOOT_MODE_BIOS:
            grubRootDev = layout.dev_rootfs
            prefix = "/boot"
        else:
            assert False

        # deal with recordfail variable
        buf += 'load_env\n'
        buf += 'if [ "${recordfail}" ] ; then\n'
        buf += '  unset stable\n'
        buf += '  save_env stable\n'
        buf += '  unset recordfail\n'
        buf += '  save_env recordfail\n'
        buf += 'fi\n'
        buf += '\n'

        # specify default menuentry and timeout
        if boot_mode == Bbki.BOOT_MODE_EFI:
            loadVideo = 'insmod efi_gop ; insmod efi_uga'
        elif boot_mode == Bbki.BOOT_MODE_BIOS:
            loadVideo = 'insmod vbe'
        else:
            assert False
        buf += '%s\n' % (loadVideo)
        buf += 'if [ "${stable}" ] ; then\n'
        buf += '  set default=0\n'
        buf += '  set timeout=%d\n' % (0 + extraTimeout)
        buf += 'else\n'
        buf += '  set default=1\n'
        buf += '  if sleep --verbose --interruptible %d ; then\n' % (3 + extraTimeout)
        buf += '    set timeout=0\n'
        buf += '  else\n'
        buf += '    set timeout=-1\n'
        buf += '  fi\n'
        buf += 'fi\n'
        buf += '\n'

        # write comments
        buf += '# These options are recorded in initramfs\n'
        buf += '#   rootfs=%s(UUID:%s)\n' % (layout.dev_rootfs, self._getBlkDevUuid(layout.dev_rootfs))
        if initCmdline != "":
            buf += '#   init=%s\n' % (initCmdline)
        buf += '\n'

        # write menu entry for stable main kernel
        buf += 'menuentry "Stable: Linux-%s" {\n' % (buildTarget.postfix)
        buf += '  set gfxpayload=keep\n'
        buf += '  set recordfail=1\n'
        buf += '  save_env recordfail\n'
        buf += '  %s\n' % (self._getGrubRootDevCmd(grubRootDev))
        buf += '  linux %s quiet %s\n' % (os.path.join(prefix, buildTarget.kernelFile), grubKernelOpt)
        buf += '  initrd %s\n' % (os.path.join(prefix, buildTarget.initrdFile))
        buf += '}\n'
        buf += '\n'

        # write menu entry for main kernel
        buf += self._grubGetMenuEntryList("Current", buildTarget, grubRootDev, prefix, grubKernelOpt)

        # write menu entry for rescue os
        if os.path.exists("/boot/rescue"):
            uuid = self._getBlkDevUuid(grubRootDev)
            kernelFile = os.path.join(prefix, "rescue", "x86_64", "vmlinuz")
            initrdFile = os.path.join(prefix, "rescue", "x86_64", "initcpio.img")
            myPrefix = os.path.join(prefix, "rescue")
            buf += self._grubGetMenuEntryList2("Rescue OS",
                                               grubRootDev,
                                               "%s dev_uuid=%s basedir=%s" % (kernelFile, uuid, myPrefix),
                                               initrdFile)

        # write menu entry for auxillary os
        for osDesc, osPart, osbPart, chain in self.getAuxOsInfo():
            buf += 'menuentry "Auxillary: %s" {\n' % (osDesc)
            buf += '  %s\n' % (self._getGrubRootDevCmd(osbPart))
            buf += '  chainloader +%d\n' % (chain)
            buf += '}\n'
            buf += '\n'

        # write menu entry for history kernels
        if os.path.exists(self._bbki._fsLayout.get_boot_history_dir()):
            for kernelFile in sorted(os.listdir(self._bbki._fsLayout.get_boot_history_dir()), reverse=True):
                if kernelFile.startswith("kernel-"):
                    buildTarget = FkmBuildTarget.newFromKernelFilename(kernelFile)
                    if os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_history_dir(), buildTarget.initrdFile)):
                        buf += self._grubGetMenuEntryList("History", buildTarget, grubRootDev, os.path.join(prefix, "history"), grubKernelOpt)

        # write menu entry for restart
        buf += 'menuentry "Restart" {\n'
        buf += '    reboot\n'
        buf += '}\n'
        buf += '\n'

        # write menu entry for restarting to UEFI setup
        if boot_mode == Bbki.BOOT_MODE_EFI:
            buf += 'menuentry "Restart to UEFI setup" {\n'
            buf += '  fwsetup\n'
            buf += '}\n'
            buf += '\n'
        elif boot_mode == Bbki.BOOT_MODE_BIOS:
            pass
        else:
            assert False

        # write menu entry for shutdown
        buf += 'menuentry "Power Off" {\n'
        buf += '    halt\n'
        buf += '}\n'
        buf += '\n'

        # write grub.cfg file
        with open("/boot/grub/grub.cfg", "w") as f:
            f.write(buf)

    def _grubGetMenuEntryList(self, title, buildTarget, grubRootDev, prefix, grubKernelOpt):
        return self._grubGetMenuEntryList2("%s: Linux-%s" % (title, buildTarget.postfix),
                                           grubRootDev,
                                           "%s %s" % (os.path.join(prefix, buildTarget.kernelFile), grubKernelOpt),
                                           os.path.join(prefix, buildTarget.initrdFile))

    def _grubGetMenuEntryList2(self, title, grubRootDev, kernelLine, initrdLine):
        buf = ''
        buf += 'menuentry "%s" {\n' % (title)
        buf += '  %s\n' % (self._getGrubRootDevCmd(grubRootDev))
        buf += '  echo "Loading Linux kernel ..."\n'
        buf += '  linux %s\n' % (kernelLine)
        buf += '  echo "Loading initial ramdisk ..."\n'
        buf += '  initrd %s\n' % (initrdLine)
        buf += '}\n'
        buf += '\n'
        return buf

    def _getGrubRootDevCmd(self, devPath):
        if os.path.dirname(devPath) == "/dev/mapper" or devPath.startswith("/dev/dm-"):
            lvmInfo = FmUtil.getBlkDevLvmInfo(devPath)
            if lvmInfo is not None:
                return "set root=(lvm/%s-%s)" % (lvmInfo[0], lvmInfo[1])

        return "search --fs-uuid --no-floppy --set %s" % (self._getBlkDevUuid(devPath))

    def _getBlkDevUuid(self, devPath):
        uuid = FmUtil.getBlkDevUuid(devPath)
        if uuid == "":
            raise Exception("device %s unsupported" % (devPath))
        return uuid





# def get_stable_flag(self):
#     # we use grub environment variable to store stable status, our grub needs this status either
#     if not os.path.exists(self._bbki._fsLayout.get_grub_dir()):
#         raise BbkiSystemError("bootloader is not installed")

#     out = Util.cmdCall("grub-editenv", self._grubEnvFile, "list")
#     return re.search("^stable=", out, re.M) is not None

# def set_stable_flag(self, value):
#     assert value is not None and isinstance(value, bool)

#     if not os.path.exists(self._bbki._fsLayout.get_grub_dir()):
#         raise BbkiSystemError("bootloader is not installed")

#     if value:
#         Util.cmdCall("grub-editenv", self._grubEnvFile, "set", "stable=1")
#     else:
#         if not os.path.exists(self._grubEnvFile):
#             return
#         Util.cmdCall("grub-editenv", self._grubEnvFile, "unset", "stable")
