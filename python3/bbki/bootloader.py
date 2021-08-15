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
from .static import BootMode
from .boot_entry import BootEntry
from .boot_entry import BootEntryUtils
from .exception import BootloaderInstallError


class BootLoaderGrub:

    def __init__(self, bbki):
        self._bbki = bbki

        self._grubCfgFile = os.path.join(self._bbki._fsLayout.get_grub_dir(), "grub.cfg")

        self._grubKernelInitCmdline = ""
        if True:
            self._grubKernelInitCmdline += " console=ttynull"                                               # global data: only use console when debug boot process
            self._grubKernelInitCmdline += " %s" % (self._bbki._targetHostInfo.aux_kernel_init_cmdline)     # host level extra data
            self._grubKernelInitCmdline += " %s" % (self._bbki.config.get_kernel_extra_init_cmdline())      # admin level extra data
            self._grubKernelInitCmdline = self._grubKernelInitCmdline.strip()

    def getMainBootEntry(self):
        if not os.path.exists(self._grubCfgFile):
            return None

        buf = pathlib.Path(self._grubCfgFile).read_text()
        m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*\n  linux \S*/kernel-(\S+) .*\n}', buf)
        if m is not None:
            return BootEntry.new_from_postfix(self._bbki, m.group(1))
        else:
            return None

    def install(self):
        if self._bbki._targetHostInfo.boot_mode == BootMode.EFI:
            self._uefiInstall()
        elif self._bbki._targetHostInfo.boot_mode == BootMode.BIOS:
            self._biosInstall()
        else:
            assert False

    def remove(self):
        if self._bbki._targetHostInfo.boot_mode == BootMode.EFI:
            self._uefiRemove()
        elif self._bbki._targetHostInfo.boot_mode == BootMode.BIOS:
            self._biosRemove()
        else:
            assert False

    def update(self):
        self.__genGrubCfg()

    def _uefiInstall(self):
        # remove old directory
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "EFI"))
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "grub"))

        # install /boot/grub and /boot/EFI directory
        # install grub into ESP
        # *NO* UEFI firmware variable is touched, so that we are portable
        Util.cmdCall("grub-install", "--removable", "--target=x86_64-efi", "--efi-directory=%s" % (self._bbki._fsLayout.get_boot_dir()), "--no-nvram")

        # generate grub.cfg
        self.__genGrubCfg()

    def _uefiRemove(self):
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "EFI"))
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "grub"))

    def _biosInstall(self):
        # remove old directory
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "grub"))

        # install /boot/grub directory
        # install grub into disk MBR
        bootDisk = Util.devPathPartitionToDisk(self._bbki._targetHostInfo.mount_point_list[0].dev_path)
        Util.cmdCall("grub-install", "--target=i386-pc", bootDisk)

        # generate grub.cfg
        self.__genGrubCfg()

    def _biosRemove(self):
        # remove MBR
        bootDisk = Util.devPathPartitionToDisk(self._bbki._targetHostInfo.mount_point_list[0].dev_path)
        with open(bootDisk, "wb+") as f:
            f.write(Util.newBuffer(0, 440))

        # remove /boot/grub directory
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "grub"))

    def __genGrubCfg(self):
        buf = ''
        if self._bbki._targetHostInfo.boot_mode == BootMode.EFI:
            grubRootDevUuid = self._bbki._targetHostInfo.mount_point_list[1].dev_uuid       # MOUNT_TYPE_BOOT
            _prefixedPath = _prefixedPathEfi
        elif self._bbki._targetHostInfo.boot_mode == BootMode.BIOS:
            grubRootDevUuid = self._bbki._targetHostInfo.mount_point_list[0].dev_uuid       # MOUNT_TYPE_ROOT
            _prefixedPath = _prefixedPathBios
        else:
            assert False
        initName, initCmdline = self._bbki.config.get_system_init_info()

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
        if self._bbki._targetHostInfo.boot_mode == BootMode.EFI:
            buf += 'insmod efi_gop\n'
            buf += 'insmod efi_uga\n'
        elif self._bbki._targetHostInfo.boot_mode == BootMode.BIOS:
            buf += 'insmod vbe\n'
        else:
            assert False
        buf += 'if [ "${stable}" ] ; then\n'
        buf += '  set default=0\n'
        buf += '  set timeout=%d\n' % (0 + self._bbki.config.get_bootloader_extra_time())
        buf += 'else\n'
        buf += '  set default=1\n'
        buf += '  if sleep --verbose --interruptible %d ; then\n' % (3 + self._bbki.config.get_bootloader_extra_time())
        buf += '    set timeout=0\n'
        buf += '  else\n'
        buf += '    set timeout=-1\n'
        buf += '  fi\n'
        buf += 'fi\n'
        buf += '\n'

        # write comments
        buf += '# These options are recorded in initramfs\n'
        buf += '#   rootfs=%s\n' % (grubRootDevUuid)
        if initCmdline != "":
            buf += '#   init=%s\n' % (initCmdline)
        buf += '\n'

        # write menu entry for main kernel
        if True:
            bootEntryList = BootEntryUtils(self._bbki).getBootEntryList()
            if len(bootEntryList) == 0:
                raise BootloaderInstallError("no main boot entry")
            if len(bootEntryList) > 1:
                raise BootloaderInstallError("multiple main boot entries")

            bootEntry = bootEntryList[0]
            if not bootEntry.has_kernel_files() or not bootEntry.has_initrd_files():
                raise BootloaderInstallError("broken main boot entry")

            buf += 'menuentry "Stable: Linux-%s" {\n' % (bootEntry.postfix)
            buf += '  set gfxpayload=keep\n'
            buf += '  set recordfail=1\n'
            buf += '  save_env recordfail\n'
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  linux %s quiet %s\n' % (_prefixedPath(bootEntry.kernel_filepath), self._grubKernelInitCmdline)
            buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

            # write menu entry for main kernel
            buf = ''
            buf += 'menuentry "Current: Linux-%s" {\n' % (bootEntry.postfix)
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  echo "Loading Linux kernel ..."\n'
            buf += '  linux %s %s\n' % (_prefixedPath(bootEntry.kernel_filepath), self._grubKernelInitCmdline)
            buf += '  echo "Loading initial ramdisk ..."\n'
            buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

        # write menu entry for rescue os
        if os.path.exists(self._bbki._fsLayout.get_boot_rescue_os_dir()):
            buf = ''
            buf += 'menuentry "Rescue OS" {\n'
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  linux %s dev_uuid=%s basedir=%s"\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_kernel_filepath()),
                                                             grubRootDevUuid,
                                                             _prefixedPath(self._bbki._fsLayout.get_boot_rescue_dir()))
            buf += '  initrd %s\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_initrd_filepath()))
            buf += '}\n'
            buf += '\n'

        # write menu entry for auxillary os
        for auxOs in self._bbki._targetHostInfo.aux_os_list:
            buf += 'menuentry "Auxillary: %s" {\n' % (auxOs.name)
            buf += '  %s\n' % (_grubRootDevCmd(auxOs.partition_uuid))
            buf += '  chainloader +%d\n' % (auxOs.chainloader_number)
            buf += '}\n'
            buf += '\n'

        # write menu entry for history kernels
        if os.path.exists(self._bbki._fsLayout.get_boot_history_dir()):
            for bootEntry in BootEntryUtils(self._bbki).getBootEntryList(True):
                if bootEntry.has_kernel_files and bootEntry.has_initrd_files():
                    buf = ''
                    buf += 'menuentry "History: Linux-%s" {\n' % (bootEntry.postfix)
                    buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
                    buf += '  echo "Loading Linux kernel ..."\n'
                    buf += '  linux %s %s\n' % (_prefixedPath(bootEntry.kernel_filepath), self._grubKernelInitCmdline)
                    buf += '  echo "Loading initial ramdisk ..."\n'
                    buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
                    buf += '}\n'
                    buf += '\n'
                else:
                    buf = ''
                    buf += 'menuentry "History: Linux-%s (Broken)" {\n' % (bootEntry.postfix)
                    buf += '}\n'
                    buf += '\n'

        # write menu entry for restart
        buf += 'menuentry "Restart" {\n'
        buf += '    reboot\n'
        buf += '}\n'
        buf += '\n'

        # write menu entry for restarting to UEFI setup
        if self._bbki._targetHostInfo.boot_mode == BootMode.EFI:
            buf += 'menuentry "Restart to UEFI setup" {\n'
            buf += '  fwsetup\n'
            buf += '}\n'
            buf += '\n'
        elif self._bbki._targetHostInfo.boot_mode == BootMode.BIOS:
            pass
        else:
            assert False

        # write menu entry for shutdown
        buf += 'menuentry "Power Off" {\n'
        buf += '    halt\n'
        buf += '}\n'
        buf += '\n'

        # write grub.cfg file
        with open(self._grubCfgFile, "w") as f:
            f.write(buf)


def _prefixedPathEfi(path):
    assert path.startswith("/boot/")
    return path[len("/boot"):]


def _prefixedPathBios(path):
    return path


def _grubRootDevCmd(devUuid):
    if devUuid.startswith("lvm/"):
        return "set root=(%s)" % (devUuid)
    else:
        return "search --fs-uuid --no-floppy --set %s" % (devUuid)


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
