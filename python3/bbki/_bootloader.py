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
from ._util import SystemMounts
from ._po import BootMode
from ._po import HostAuxOs
from ._kernel import BootEntryUtils
from ._exception import BootloaderInstallError


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
        self._bootDiskId = None
        self._parseGrubCfg()

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
        postfix = self._parseGrubCfgMainBootPostfix(buf)
        return BootEntryUtils(self._bbki).new_from_postfix(postfix)

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

    def install(self, boot_mode, rootfs_dev=None, rootfs_dev_uuid=None, esp_dev=None, esp_dev_uuid=None, boot_disk=None, boot_disk_id=None, aux_os_list=[], aux_kernel_init_cmdline=""):
        assert self._status != self.STATUS_INVALID
        if boot_mode == BootMode.EFI:
            assert rootfs_dev is not None and rootfs_dev_uuid is not None
            assert esp_dev is not None and esp_dev_uuid is not None
            assert boot_disk is None and boot_disk_id is None
            if rootfs_dev != SystemMounts().find_root_entry().dev:
                raise ValueError("invalid rootfs mount point")
            if esp_dev != SystemMounts().find_entry_by_mount_point(self._bbki._fsLayout.get_boot_dir()).dev:
                raise ValueError("invalid ESP partition mount point")
            if self._status == self.STATUS_NORMAL:
                if boot_mode != self._bootMode:
                    raise ValueError("boot mode and bootloader is different")
                if rootfs_dev != self._rootfsDev:
                    raise ValueError("rootfs device and bootloader is different")
                if esp_dev != self._espDev:
                    raise ValueError("ESP partition and bootloader is different")
        elif boot_mode == BootMode.BIOS:
            assert rootfs_dev is not None and rootfs_dev_uuid is not None
            assert esp_dev is None and esp_dev_uuid is None
            assert boot_disk is not None and boot_disk_id is not None
            if rootfs_dev != SystemMounts().find_root_entry().dev:
                raise ValueError("invalid rootfs mount point")
            if boot_disk != Util.devPathPartitionOrDiskToDisk(rootfs_dev):
                raise ValueError("invalid boot disk")
            if self._status == self.STATUS_NORMAL:
                if boot_mode != self._bootMode:
                    raise ValueError("boot mode and bootloader is different")
                if rootfs_dev != self._rootfsDev:
                    raise ValueError("rootfs device and bootloader is different")
                if boot_disk != self._bootDisk:
                    raise ValueError("boot disk and bootloader is different")
        else:
            assert False

        # generate grub.cfg
        # may raise exception
        buf = self._genGrubCfg(boot_mode, rootfs_dev_uuid, esp_dev_uuid, boot_disk_id, aux_os_list, self._getKernelCmdLine(aux_kernel_init_cmdline))

        # install grub binaries
        if boot_mode == BootMode.EFI:
            # install /boot/grub and /boot/EFI directory
            # install grub into ESP
            # *NO* UEFI firmware variable is touched, so that we are portable
            Util.cmdCall("grub-install", "--removable", "--target=x86_64-efi", "--efi-directory=%s" % (self._bbki._fsLayout.get_boot_dir()), "--no-nvram")
        elif boot_mode == BootMode.BIOS:
            # install /boot/grub directory
            # install grub into disk MBR
            Util.cmdCall("grub-install", "--target=i386-pc", boot_disk)
        else:
            assert False

        # write grub.cfg file
        with open(self._grubCfgFile, "w") as f:
            f.write(buf)

        # record variable value
        self._status = self.STATUS_NORMAL
        self._bootMode = boot_mode
        self._rootfsDev = rootfs_dev
        self._rootfsDevUuid = rootfs_dev_uuid
        self._espDev = esp_dev
        self._espDevUuid = esp_dev_uuid
        self._bootDisk = boot_disk
        self._bootDiskId = boot_disk_id

    def update(self, aux_os_list, aux_kernel_init_cmdline):
        assert self._status == self.STATUS_NORMAL

        # parameters
        buf = pathlib.Path(self._grubCfgFile).read_text()
        if aux_os_list is not None:
            auxOsList = aux_os_list
        else:
            auxOsList = self._parseGrubCfgAuxOsList(buf)
        if aux_kernel_init_cmdline is not None:
            kernelCmdLine = self._getKernelCmdLine(aux_kernel_init_cmdline)
        else:
            kernelCmdLine = self._parseGrubCfgKernelCmdLine(buf)

        # generate grub.cfg
        # may raise exception
        buf = self._genGrubCfg(self._bootMode, self._rootfsDevUuid, self._espDevUuid, auxOsList, kernelCmdLine)

        # write grub.cfg file
        with open(self._grubCfgFile, "w") as f:
            f.write(buf)

    def remove(self):
        if self._status == self.STATUS_NORMAL:
            if self._bootMode == BootMode.EFI:
                if self._rootfsDev != SystemMounts().find_root_entry().dev:
                    raise ValueError("invalid rootfs mount point")
                if self._espDev != SystemMounts().find_entry_by_mount_point(self._bbki._fsLayout.get_boot_dir()).dev:
                    raise ValueError("invalid ESP partition mount point")
            elif self._bootMode == BootMode.BIOS:
                if self._rootfsDev != SystemMounts().find_root_entry().dev:
                    raise ValueError("invalid rootfs mount point")
                if self._bootDisk != Util.devPathPartitionOrDiskToDisk(self._rootfsDev):
                    raise ValueError("invalid boot disk")

        # remove MBR
        # MBR may not be correctly removed when status==STATUS_INVALID
        if self._status == self.STATUS_NORMAL:
            if self._bootMode == BootMode.BIOS:
                with open(self._bootDisk, "wb+") as f:
                    f.write(b'\x00' * 440)

        # delete files
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_dir())
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_efi_dir())

        # clear variables
        self._bootDiskId = None
        self._bootDisk = None
        self._espDevUuid = None
        self._espDev = None
        self._rootfsDevUuid = None
        self._rootfsDev = None
        self._bootMode = None
        self._status = self.STATUS_NOT_INSTALLED

    def _getKernelCmdLine(self, aux_kernel_init_cmdline):
        kernelCmdLine = ""
        kernelCmdLine += " console=ttynull"                                               # global data: only use console when debug boot process
        kernelCmdLine += " %s" % (aux_kernel_init_cmdline)                                # host level extra data
        kernelCmdLine += " %s" % (self._bbki.config.get_kernel_extra_init_cmdline())      # admin level extra data
        kernelCmdLine = kernelCmdLine.strip()
        return kernelCmdLine

    def _parseGrubCfg(self):
        assert self._status is None

        if not os.path.exists(self._bbki._fsLayout.get_boot_grub_dir()):
            self._status = self.STATUS_NOT_INSTALLED
            return

        if not os.path.exists(self._grubCfgFile):
            self._status = self.STATUS_INVALID
            return
        if not Util.cmdCallTestSuccess("grub-script-check", self._grubCfgFile):
            self._status = self.STATUS_INVALID
            return
        buf = pathlib.Path(self._grubCfgFile).read_text()

        m = re.search(r'#   rootfs device UUID: (\S+)', buf, re.M)
        if m is None:
            self._status = self.STATUS_INVALID
            return
        rootfsDevUuid = m.group(1)
        rootfsDev = Util.getBlkDevByUuid(rootfsDevUuid)

        espDevUuid = None
        espDev = None
        bootDiskId = None
        bootDisk = None
        if os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "x86_64-efi")):
            if not os.path.exists(self._bbki._fsLayout.get_boot_grub_efi_dir()):
                self._status = self.STATUS_INVALID
                return

            bootMode = BootMode.EFI

            m = re.search(r'#   ESP partition UUID: (\S+)', buf, re.M)
            if m is None:
                self._status = self.STATUS_INVALID
                return
            espDevUuid = m.group(1)
            espDev = Util.getBlkDevByUuid(espDevUuid)
        elif os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "i386-pc")):
            bootMode = BootMode.BIOS

            m = re.search(r'#   boot disk ID: (\S+)', buf, re.M)
            if m is None:
                self._status = self.STATUS_INVALID
                return
            bootDiskId = m.group(1)
            bootDisk = Util.getDiskById(bootDiskId)
        else:
            assert False

        self._status = self.STATUS_NORMAL
        self._bootMode = bootMode
        self._rootfsDev = rootfsDev
        self._rootfsDevUuid = rootfsDevUuid
        self._espDev = espDev
        self._espDevUuid = espDevUuid
        self._bootDisk = bootDisk
        self._bootDiskId = bootDiskId

    def _genGrubCfg(self, bootMode, rootfsDevUuid, espDevUuid, bootDiskId, auxOsList, kernelCmdLine):
        buf = ''
        if bootMode == BootMode.EFI:
            grubRootDevUuid = rootfsDevUuid
            _prefixedPath = _prefixedPathEfi
        elif bootMode == BootMode.BIOS:
            grubRootDevUuid = espDevUuid
            _prefixedPath = _prefixedPathBios
        else:
            assert False
        initCmdLine = self._bbki.config.get_system_init().cmd

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
        if bootMode == BootMode.EFI:
            buf += 'insmod efi_gop\n'
            buf += 'insmod efi_uga\n'
        elif bootMode == BootMode.BIOS:
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
        if bootMode == BootMode.EFI:
            buf += '#   rootfs device UUID: %s\n' % (rootfsDevUuid)
            buf += '#   ESP partition UUID: %s\n' % (espDevUuid)
        elif bootMode == BootMode.BIOS:
            buf += '#   rootfs device UUID: %s\n' % (rootfsDevUuid)
            buf += '#   boot disk ID: %s\n' % (bootDiskId)
        else:
            assert False
        if initCmdLine != "":
            buf += '#   init command line: %s\n' % (initCmdLine)
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
            buf += '  linux %s quiet %s\n' % (_prefixedPath(bootEntry.kernel_filepath), kernelCmdLine)
            buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

            # write menu entry for main kernel
            buf += 'menuentry "Current: Linux-%s" {\n' % (bootEntry.postfix)
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  echo "Loading Linux kernel ..."\n'
            buf += '  linux %s %s\n' % (_prefixedPath(bootEntry.kernel_filepath), kernelCmdLine)
            buf += '  echo "Loading initial ramdisk ..."\n'
            buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

        # write menu entry for rescue os
        if os.path.exists(self._bbki._fsLayout.get_boot_rescue_os_dir()):
            buf += 'menuentry "Rescue OS" {\n'
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  linux %s dev_uuid=%s basedir=%s"\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_kernel_filepath()),
                                                             grubRootDevUuid,
                                                             _prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_dir()))
            buf += '  initrd %s\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_initrd_filepath()))
            buf += '}\n'
            buf += '\n'

        # write menu entry for auxillary os
        for auxOs in auxOsList:
            buf += 'menuentry "Auxillary: %s" {\n' % (auxOs.name)
            buf += '  %s\n' % (_grubRootDevCmd(auxOs.partition_uuid))
            buf += '  chainloader +%d\n' % (auxOs.chainloader_number)
            buf += '}\n'
            buf += '\n'

        # write menu entry for history kernels
        if os.path.exists(self._bbki._fsLayout.get_boot_history_dir()):
            for bootEntry in BootEntryUtils(self._bbki).getBootEntryList(True):
                if bootEntry.has_kernel_files and bootEntry.has_initrd_files():
                    buf += 'menuentry "History: Linux-%s" {\n' % (bootEntry.postfix)
                    buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
                    buf += '  echo "Loading Linux kernel ..."\n'
                    buf += '  linux %s %s\n' % (_prefixedPath(bootEntry.kernel_filepath), kernelCmdLine)
                    buf += '  echo "Loading initial ramdisk ..."\n'
                    buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
                    buf += '}\n'
                    buf += '\n'
                else:
                    buf += 'menuentry "History: Linux-%s (Broken)" {\n' % (bootEntry.postfix)
                    buf += '}\n'
                    buf += '\n'

        # write menu entry for restart
        buf += 'menuentry "Restart" {\n'
        buf += '    reboot\n'
        buf += '}\n'
        buf += '\n'

        # write menu entry for restarting to UEFI setup
        if bootMode == BootMode.EFI:
            buf += 'menuentry "Restart to UEFI setup" {\n'
            buf += '  fwsetup\n'
            buf += '}\n'
            buf += '\n'
        elif bootMode == BootMode.BIOS:
            pass
        else:
            assert False

        # write menu entry for shutdown
        buf += 'menuentry "Power Off" {\n'
        buf += '    halt\n'
        buf += '}\n'
        buf += '\n'

        return buf

    def _parseGrubCfgMainBootPostfix(self, buf):
        m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*\n  linux \S*/kernel-(\S+) .*\n}', buf)
        return m.group(1)

    def _parseGrubCfgAuxOsList(self, buf):
        ret = []
        for m in re.finditer(r'menuentry "Auxillary: (.*)" {\n  search --fs-uuid --no-floppy --set (\S+)\n  chainloader +([0-9]+)\n}', buf):
            ret.append(HostAuxOs(m.group(1), m.group(2), m.group(3)))
        return ret

    def _parseGrubCfgKernelCmdLine(self, buf):
        m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*\n  linux \S+ quiet (.*)\n}', buf)
        return m.group(1)


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
