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
import pathlib
import robust_layer.simple_fops
from ._util import Util
from ._po import BootMode
from ._boot_entry import BootEntry
from ._kernel import BootEntryUtils
from ._exception import BootloaderInstallError
from ._exception import RunningEnvironmentError


class BootLoader:

    STATUS_NORMAL = 1
    STATUS_INVALID = 2
    STATUS_NOT_INSTALLED = 3

    def __init__(self, bbki):
        self._bbki = bbki

        self._grubCfgFile = os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "grub.cfg")
        self._grubEnvFile = os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "grubenv")

        self._status = None
        self._bootMode = None
        self._rootfsDev = None
        self._rootfsDevUuid = None
        self._espDev = None
        self._espDevUuid = None
        self._bootDisk = None
        self._bootDiskPtuuid = None
        self._initCmdLine = None
        self._parseGrub()

        # var for install() only
        self._targetHostInfo = None
        self._grubKernelInitCmdline = None

    def getStatus(self):
        return self._status

    def getBootMode(self):
        assert self._status == self.STATUS_NORMAL
        return self._bootMode

    def getFilePathList(self):
        assert self._status == self.STATUS_NORMAL

        myBootMode = self.getBootMode()
        ret = []
        ret += glob.glob(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "*"), recursive=True)
        if myBootMode == BootMode.EFI:
            ret += glob.glob(os.path.join(self._bbki._fsLayout.get_boot_grub_efi_dir(), "*"), recursive=True)
        elif myBootMode == BootMode.BIOS:
            pass
        else:
            assert False
        return ret

    def getMainBootEntry(self):
        assert self._status == self.STATUS_NORMAL

        buf = pathlib.Path(self._grubCfgFile).read_text()
        m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*\n  linux \S*/kernel-(\S+) .*\n}', buf)
        if m is not None:
            return BootEntry.new_from_postfix(self._bbki, m.group(1))
        else:
            return None

    def getStableFlag(self):
        assert self._status == self.STATUS_NORMAL

        out = Util.cmdCall("grub-editenv", self._grubEnvFile, "list")
        return re.search("^stable=", out, re.M) is not None

    def setStableFlag(self, value):
        assert self._status == self.STATUS_NORMAL
        assert value is not None and isinstance(value, bool)

        if value:
            Util.cmdCall("grub-editenv", self._grubEnvFile, "set", "stable=1")
        else:
            if not os.path.exists(self._grubEnvFile):
                return
            Util.cmdCall("grub-editenv", self._grubEnvFile, "unset", "stable")

    def install(self, boot_mode, rootfs_dev=None, esp_dev=None, boot_disk=None, aux_kernel_init_cmdline=""):
        assert boot_mode in [BootMode.EFI, BootMode.BIOS]

        if self._status == self.STATUS_NORMAL and not self._bootMode == boot_mode:
            raise ValueError("boot mode and bootloader is different")

        if boot_mode == BootMode.EFI:
            if rootfs_dev != Util.getMountDeviceForPath("/"):
               raise ValueError("invalid rootfs mount point")
            if esp_dev != Util.getMountDeviceForPath("/boot"):
                raise ValueError("invalid ESP partition mount point")
        elif boot_mode == BootMode.BIOS:
            if rootfs_dev != Util.getMountDeviceForPath("/"):
                raise ValueError("invalid rootfs mount point")
            if boot_disk != Util.devPathPartitionOrDiskToDisk(rootfs_dev):
                raise ValueError("invalid boot device")
        else:
            assert False

        grubKernelInitCmdline = ""
        if True:
            grubKernelInitCmdline += " console=ttynull"                                               # global data: only use console when debug boot process
            grubKernelInitCmdline += " %s" % (aux_kernel_init_cmdline)                                # host level extra data
            grubKernelInitCmdline += " %s" % (self._bbki.config.get_kernel_extra_init_cmdline())      # admin level extra data
            grubKernelInitCmdline = grubKernelInitCmdline.strip()

        rootfsDevUuid = None
        espDevUuid = None
        bootDiskPtUuid = None

        if boot_mode == BootMode.EFI:
            rootfsDevUuid = Util.getBlkDevUuid(rootfs_dev) if rootfs_dev is not None else None
            espDevUuid = Util.getBlkDevUuid(esp_dev) if esp_dev is not None else None
            self._uefiInstall(rootfs_dev, rootfsDevUuid, esp_dev, espDevUuid, grubKernelInitCmdline)
        elif boot_mode == BootMode.BIOS:
            espDevUuid = Util.getBlkDevUuid(esp_dev) if esp_dev is not None else None
            bootDiskPtUuid = Util.getBlkDevPtUuid(boot_disk) if boot_disk is not None else None
            self._biosInstall(rootfs_dev, rootfsDevUuid, boot_disk, bootDiskPtUuid, grubKernelInitCmdline)
        else:
            assert False

        self._status = self.STATUS_NORMAL
        self._bootMode = boot_mode
        self._rootfsDev = rootfs_dev
        self._rootfsDevUuid = rootfsDevUuid
        self._espDev = esp_dev
        self._espDevUuid = espDevUuid
        self._bootDisk = boot_disk
        self._bootDiskPtuuid = bootDiskPtUuid
        self._initCmdLine = grubKernelInitCmdline

    def remove(self):
        # check 
        if self._status == self.STATUS_NORMAL:
            if self._bootMode == BootMode.EFI:
                if self._rootfsDev != Util.getMountDeviceForPath("/"):
                    raise ValueError("invalid rootfs mount point")
                if self._espDev != Util.getMountDeviceForPath("/boot"):
                    raise ValueError("invalid ESP partition mount point")
            elif self._bootMode == BootMode.BIOS:
                if self._rootfsDev != Util.getMountDeviceForPath("/"):
                    raise ValueError("invalid rootfs mount point")
                if self._bootDisk != Util.devPathPartitionOrDiskToDisk(self._rootfsDev):
                    raise ValueError("invalid boot device")

        # remove MBR, MBR may not be removed for STATUS_INVALID
        if self._status == self.STATUS_NORMAL and self._bootMode == BootMode.BIOS:
            with open(self._bootDisk, "wb+") as f:
                f.write(Util.newBuffer(0, 440))

        # delete files
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_dir())
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_efi_dir())

        # clear variables
        self._initCmdLine = None
        self._bootDiskPtuuid = None
        self._bootDisk = None
        self._espDevUuid = None
        self._espDev = None
        self._rootfsDevUuid = None
        self._rootfsDev = None
        self._bootMode = None
        self._status = self.STATUS_NOT_INSTALLED

    def _uefiInstall(self, rootfsDev, espDev, grubKernelInitCmdline):
        # remove old directory
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_dir())
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_efi_dir())

        # install /boot/grub and /boot/EFI directory
        # install grub into ESP
        # *NO* UEFI firmware variable is touched, so that we are portable
        Util.cmdCall("grub-install", "--removable", "--target=x86_64-efi", "--efi-directory=%s" % (self._bbki._fsLayout.get_boot_dir()), "--no-nvram")

        # generate grub.cfg
        self._genGrubCfg()

    def _biosInstall(self):
        # remove old directory
        robust_layer.simple_fops.rm(os.path.join(self._bbki._fsLayout.get_boot_dir(), "grub"))

        # install /boot/grub directory
        # install grub into disk MBR
        bootDisk = Util.devPathPartitionOrDiskToDisk(self._targetHostInfo.mount_point_list[0].dev_path)
        Util.cmdCall("grub-install", "--target=i386-pc", bootDisk)

        # generate grub.cfg
        self._genGrubCfg()

    def _parseGrub(self):
        self._status = None
        self._bootMode = None
        self._rootfsDev = None
        self._espDev = None
        self._bootDisk = None
        self._initCmdLine = None

        if not os.path.exists(self._bbki._fsLayout.get_boot_grub_dir()):
            self._status = self.STATUS_NOT_INSTALLED
            return

        if not os.path.exists(self._grubCfgFile):
            self._status = self.STATUS_INVALID
            return

        if os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "x86_64-efi")):
            if not os.path.exists(self._bbki._fsLayout.get_boot_grub_efi_dir()):
                self._status = self.STATUS_INVALID
                return






        self._rootfsDev = None
        self._espDev = None
        self._bootDisk = None
        self._initCmdLine = None


        if self._targetHostInfo.boot_mode == BootMode.EFI:
            buf += '#   rootfs device UUID: %s\n' % (self._targetHostInfo.mount_point_list[0].dev_uuid)        # MOUNT_TYPE_ROOT
            buf += '#   ESP partition UUID: %s\n' % (self._targetHostInfo.mount_point_list[1].dev_uuid)        # MOUNT_TYPE_BOOT
        elif self._targetHostInfo.boot_mode == BootMode.BIOS:
            buf += '#   rootfs device UUID: %s\n' % (self._targetHostInfo.mount_point_list[0].dev_uuid)        # MOUNT_TYPE_ROOT
        else:
            assert False



            self._status = self.STATUS_NORMAL
            self._boot_mode = BootMode.EFI
            return

        if os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "i386-pc")):
            self._status = self.STATUS_NORMAL
            self._bootMode = BootMode.BIOS
            return

        self._status = self.STATUS_INVALID
        return

    def _genGrubCfg(self):
        buf = ''
        if self._targetHostInfo.boot_mode == BootMode.EFI:
            grubRootDevUuid = self._targetHostInfo.mount_point_list[1].dev_uuid       # MOUNT_TYPE_BOOT
            _prefixedPath = _prefixedPathEfi
        elif self._targetHostInfo.boot_mode == BootMode.BIOS:
            grubRootDevUuid = self._targetHostInfo.mount_point_list[0].dev_uuid       # MOUNT_TYPE_ROOT
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
        if self._targetHostInfo.boot_mode == BootMode.EFI:
            buf += 'insmod efi_gop\n'
            buf += 'insmod efi_uga\n'
        elif self._targetHostInfo.boot_mode == BootMode.BIOS:
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
        buf += '# Parameters:\n'
        if self._targetHostInfo.boot_mode == BootMode.EFI:
            buf += '#   rootfs device UUID: %s\n' % (self._targetHostInfo.mount_point_list[0].dev_uuid)        # MOUNT_TYPE_ROOT
            buf += '#   ESP partition UUID: %s\n' % (self._targetHostInfo.mount_point_list[1].dev_uuid)        # MOUNT_TYPE_BOOT
        elif self._targetHostInfo.boot_mode == BootMode.BIOS:
            buf += '#   rootfs device UUID: %s\n' % (self._targetHostInfo.mount_point_list[0].dev_uuid)        # MOUNT_TYPE_ROOT
            buf += '#   boot disk PTUUID: %s\n' % (self._targetHostInfo.mount_point_list[0].dev_uuid)        # MOUNT_TYPE_ROOT
        else:
            assert False
        if initCmdline != "":
            buf += '#   init program: %s\n' % (initCmdline)
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
        for auxOs in self._targetHostInfo.aux_os_list:
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
        if self._targetHostInfo.boot_mode == BootMode.EFI:
            buf += 'menuentry "Restart to UEFI setup" {\n'
            buf += '  fwsetup\n'
            buf += '}\n'
            buf += '\n'
        elif self._targetHostInfo.boot_mode == BootMode.BIOS:
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


# def _getBackgroundFileInfo(self):
#     for fn in glob.glob("/boot/background.*"):
#         fn = fn.replace("/boot", "")
#         if fn.endswith(".png"):
#             return (fn, "png")
#         elif fn.endswith(".jpg"):
#             return (fn, "jpg")
#     return None
