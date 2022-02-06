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
from ._util import Util
from ._util import PhysicalDiskMounts
from ._po import BootMode
from ._po import HostAuxOs
from ._boot_entry import BootEntryUtils
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
        self._mainBootPostfix = None
        self._kernelCmdLine = None
        self._invalidReason = None
        self._parseGrubCfg()

    def getStatus(self):
        return self._status

    def getInvalidReason(self):
        assert self._status == self.STATUS_INVALID
        return self._invalidReason

    def getBootMode(self):
        assert self._status == self.STATUS_NORMAL
        return self._bootMode

    def get_filepaths(self):
        assert self._status == self.STATUS_NORMAL

        ret = []
        ret += Util.globDirRecursively(self._bbki._fsLayout.get_boot_grub_dir())
        if self._bootMode == BootMode.EFI:
            ret += Util.globDirRecursively(self._bbki._fsLayout.get_boot_grub_efi_dir())
        elif self._bootMode == BootMode.BIOS:
            pass
        else:
            assert False
        return ret

    def getMainBootEntry(self):
        assert self._status == self.STATUS_NORMAL

        return BootEntryUtils(self._bbki).new_from_postfix(self._mainBootPostfix)

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

    def install(self, boot_mode, rootfs_dev, rootfs_dev_uuid, esp_dev, esp_dev_uuid, boot_disk, boot_disk_id, main_boot_entry, aux_os_list, aux_kernel_init_cmdline, bForce=False):
        if boot_mode == BootMode.EFI:
            assert rootfs_dev is not None and rootfs_dev_uuid is not None
            assert esp_dev is not None and esp_dev_uuid is not None
            assert boot_disk is None and boot_disk_id is None
        elif boot_mode == BootMode.BIOS:
            assert rootfs_dev is not None and rootfs_dev_uuid is not None
            assert esp_dev is None and esp_dev_uuid is None
            assert boot_disk is not None and boot_disk_id is not None
        else:
            assert False
        assert main_boot_entry.has_kernel_files() and main_boot_entry.has_initrd_files()
        assert not main_boot_entry.is_historical()

        bDifferent = False
        if boot_mode == BootMode.EFI:
            if rootfs_dev != PhysicalDiskMounts.find_root_entry().dev:
                raise ValueError("invalid rootfs mount point")
            if esp_dev != PhysicalDiskMounts.find_entry_by_mount_point(self._bbki._fsLayout.get_boot_dir()).dev:
                raise ValueError("invalid ESP partition mount point")
            if self._status == self.STATUS_NORMAL:
                if boot_mode != self._bootMode:
                    if not bForce:
                        raise ValueError("boot mode and bootloader is different")
                    else:
                        bDifferent = True
                if rootfs_dev != self._rootfsDev:
                    if not bForce:
                        raise ValueError("rootfs device and bootloader is different")
                    else:
                        bDifferent = True
                if esp_dev != self._espDev:
                    if not bForce:
                        raise ValueError("ESP partition and bootloader is different")
                    else:
                        bDifferent = True
        elif boot_mode == BootMode.BIOS:
            if rootfs_dev != PhysicalDiskMounts.find_root_entry().dev:
                raise ValueError("invalid rootfs mount point")
            if boot_disk != Util.devPathPartitionOrDiskToDisk(rootfs_dev):
                raise ValueError("invalid boot disk")
            if self._status == self.STATUS_NORMAL:
                if boot_mode != self._bootMode:
                    if not bForce:
                        raise ValueError("boot mode and bootloader is different")
                    else:
                        bDifferent = True
                if rootfs_dev != self._rootfsDev:
                    if not bForce:
                        raise ValueError("rootfs device and bootloader is different")
                    else:
                        bDifferent = True
                if boot_disk != self._bootDisk:
                    if not bForce:
                        raise ValueError("boot disk and bootloader is different")
                    else:
                        bDifferent = True
        else:
            assert False

        # generate grub.cfg
        # may raise exception
        kernelCmdLine = self._getKernelCmdLine(aux_kernel_init_cmdline)
        buf = self._genGrubCfg(boot_mode, rootfs_dev_uuid, esp_dev_uuid, boot_disk_id, main_boot_entry, aux_os_list, kernelCmdLine)

        # remove if needed
        if self._status == self.STATUS_NORMAL:
            if bDifferent:
                self.remove(bForce=True)
        elif self._status == self.STATUS_NOT_INSTALLED:
            pass
        elif self._status == self.STATUS_INVALID:
            self.remove(bForce=True)
        else:
            assert False

        # install grub binaries if needed
        if self._status == self.STATUS_NORMAL:
            pass
        elif self._status == self.STATUS_NOT_INSTALLED:
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
        self._mainBootPostfix = main_boot_entry.postfix
        self._kernelCmdLine = kernelCmdLine
        self._invalidReason = None

    def update(self, main_boot_entry, aux_os_list, aux_kernel_init_cmdline):
        assert self._status == self.STATUS_NORMAL

        # parameters
        buf = pathlib.Path(self._grubCfgFile).read_text()
        if main_boot_entry is None:
            # use original value
            mainBootEntry = BootEntryUtils(self._bbki).new_from_postfix(self._mainBootPostfix)
        else:
            assert main_boot_entry.has_kernel_files() and main_boot_entry.has_initrd_files()
            assert not main_boot_entry.is_historical()
            mainBootEntry = main_boot_entry
        if aux_os_list is None:
            # use original value
            auxOsList = self._parseGrubCfgAuxOsList(buf)
        else:
            auxOsList = aux_os_list
        if aux_kernel_init_cmdline is None:
            # use original value
            kernelCmdLine = self._kernelCmdLine
        else:
            kernelCmdLine = self._getKernelCmdLine(aux_kernel_init_cmdline)

        # generate grub.cfg
        # may raise exception
        buf = self._genGrubCfg(self._bootMode, self._rootfsDevUuid, self._espDevUuid, self._bootDiskId, mainBootEntry, auxOsList, kernelCmdLine)

        # write grub.cfg file
        with open(self._grubCfgFile, "w") as f:
            f.write(buf)

        # update record variables
        self._mainBootPostfix = mainBootEntry.postfix
        self._kernelCmdLine = kernelCmdLine

    def remove(self, bForce=False):
        bDifferent = False
        if self._status == self.STATUS_NORMAL:
            if self._bootMode == BootMode.EFI:
                if self._rootfsDev != PhysicalDiskMounts.find_root_entry().dev:
                    if not bForce:
                        raise ValueError("invalid rootfs mount point")
                    else:
                        bDifferent = True
                if self._espDev != PhysicalDiskMounts.find_entry_by_mount_point(self._bbki._fsLayout.get_boot_dir()).dev:
                    if not bForce:
                        raise ValueError("invalid ESP partition mount point")
                    else:
                        bDifferent = True
            elif self._bootMode == BootMode.BIOS:
                if self._rootfsDev != PhysicalDiskMounts.find_root_entry().dev:
                    if not bForce:
                        raise ValueError("invalid rootfs mount point")
                    else:
                        bDifferent = True
                if self._bootDisk != Util.devPathPartitionOrDiskToDisk(self._rootfsDev):
                    if not bForce:
                        raise ValueError("invalid boot disk")
                    else:
                        bDifferent = True
            else:
                assert False

        # remove MBR
        # MBR may not be correctly removed when status==STATUS_INVALID
        if self._status == self.STATUS_NORMAL and not bDifferent:
            if self._bootMode == BootMode.BIOS:
                with open(self._bootDisk, "wb+") as f:
                    f.write(b'\x00' * 440)

        # delete files
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_dir())
        robust_layer.simple_fops.rm(self._bbki._fsLayout.get_boot_grub_efi_dir())

        # clear variables
        self._status = self.STATUS_NOT_INSTALLED
        self._bootMode = None
        self._rootfsDev = None
        self._rootfsDevUuid = None
        self._espDev = None
        self._espDevUuid = None
        self._bootDisk = None
        self._bootDiskId = None
        self._mainBootPostfix = None
        self._kernelCmdLine = None
        self._invalidReason = None

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

        try:
            self._status = self.STATUS_NORMAL

            if not os.path.exists(self._grubCfgFile):
                raise _InternalParseError("\"%s\" does not exist" % (self._grubCfgFile))
            if not Util.cmdCallTestSuccess("grub-script-check", self._grubCfgFile):
                raise _InternalParseError("\"%s\" is invalid" % (self._grubCfgFile))
            buf = pathlib.Path(self._grubCfgFile).read_text()

            m = re.search(r'#   rootfs device: (\S+)', buf, re.M)
            if m is None:
                raise _InternalParseError("no rootfs device UUID in \"%s\"" % (self._grubCfgFile))
            self._rootfsDevUuid = m.group(1)
            self._rootfsDev = Util.getBlkDevByUuid(self._rootfsDevUuid)
            if self._rootfsDev is None:
                raise _InternalParseError("rootfs device %s can not be found" % (self._rootfsDevUuid))

            if os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "x86_64-efi")):
                self._bootMode = BootMode.EFI

                if not os.path.exists(self._bbki._fsLayout.get_boot_grub_efi_dir()):
                    raise _InternalParseError("\"%s\" does not exist" % (self._bbki._fsLayout.get_boot_grub_efi_dir()))

                m = re.search(r'#   ESP partition: (\S+)', buf, re.M)
                if m is None:
                    raise _InternalParseError("no ESP partition UUID in \"%s\"" % (self._grubCfgFile))
                self._espDevUuid = m.group(1)
                self._espDev = Util.getBlkDevByUuid(self._espDevUuid)
                if self._espDev is None:
                    raise _InternalParseError("ESP partition %s can not be found" % (self._espDevUuid))
            elif os.path.exists(os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "i386-pc")):
                self._bootMode = BootMode.BIOS

                m = re.search(r'#   boot disk ID: (\S+)', buf, re.M)
                if m is None:
                    raise _InternalParseError("no boot disk ID in \"%s\"" % (self._grubCfgFile))
                self._bootDiskId = m.group(1)
                self._bootDisk = Util.getDiskById(self._bootDiskId)
                if self._bootDisk is None:
                    raise _InternalParseError("boot disk %s can not be found" % (self._bootDiskId))
            else:
                assert False

            m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*?\n  linux \S*/kernel-(\S+) quiet (.*?)\n', buf, re.S)
            if m is None:
                raise _InternalParseError("no main boot entry in \"%s\"" % (self._grubCfgFile))
            self._mainBootPostfix = m.group(1)
            self._kernelCmdLine = m.group(2)
        except _InternalParseError as e:
            self._status = self.STATUS_INVALID
            self._bootMode = None
            self._rootfsDev = None
            self._rootfsDevUuid = None
            self._espDev = None
            self._espDevUuid = None
            self._bootDisk = None
            self._bootDiskId = None
            self._mainBootPostfix = None
            self._kernelCmdLine = None
            self._invalidReason = e.message

    def _genGrubCfg(self, bootMode, rootfsDevUuid, espDevUuid, bootDiskId, mainBootEntry, auxOsList, kernelCmdLine):
        buf = ''

        grubRootDevUuid = None
        _prefixedPath = None
        if bootMode == BootMode.EFI:
            grubRootDevUuid = espDevUuid
            _prefixedPath = _prefixedPathEfi
        elif bootMode == BootMode.BIOS:
            grubRootDevUuid = rootfsDevUuid
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
            buf += '#   rootfs device: %s\n' % (rootfsDevUuid)
            buf += '#   ESP partition: %s\n' % (espDevUuid)
        elif bootMode == BootMode.BIOS:
            buf += '#   rootfs device: %s\n' % (rootfsDevUuid)
            buf += '#   boot disk ID: %s\n' % (bootDiskId)
        else:
            assert False
        if initCmdLine != "":
            buf += '#   init command line: %s\n' % (initCmdLine)
        buf += '\n'

        # write menu entry for main kernel
        if True:
            buf += 'menuentry "Stable: Linux-%s" {\n' % (mainBootEntry.postfix)
            buf += '  set gfxpayload=keep\n'
            buf += '  set recordfail=1\n'
            buf += '  save_env recordfail\n'
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  linux %s quiet %s\n' % (_prefixedPath(mainBootEntry.kernel_filepath), kernelCmdLine)
            buf += '  initrd %s\n' % (_prefixedPath(mainBootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

            # write menu entry for main kernel
            buf += 'menuentry "Current: Linux-%s" {\n' % (mainBootEntry.postfix)
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  echo "Loading Linux kernel ..."\n'
            buf += '  linux %s %s\n' % (_prefixedPath(mainBootEntry.kernel_filepath), kernelCmdLine)
            buf += '  echo "Loading initial ramdisk ..."\n'
            buf += '  initrd %s\n' % (_prefixedPath(mainBootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

        # write menu entry for rescue os
        if os.path.exists(self._bbki._fsLayout.get_boot_rescue_os_dir()):
            if not os.path.exists(self._bbki._fsLayout.get_boot_rescue_os_kernel_filepath()):
                raise BootloaderInstallError("no rescue os kernel found")
            if not os.path.exists(self._bbki._fsLayout.get_boot_rescue_os_initrd_filepath()):
                raise BootloaderInstallError("no rescue os initrd found")

            buf += 'menuentry "Rescue OS" {\n'
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  linux %s dev_uuid=%s basedir=%s\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_kernel_filepath()),
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
        for bootEntry in self._bbki.get_history_boot_entries():
            buf += 'menuentry "History: Linux-%s" {\n' % (bootEntry.postfix)
            buf += '  %s\n' % (_grubRootDevCmd(grubRootDevUuid))
            buf += '  echo "Loading Linux kernel ..."\n'
            buf += '  linux %s %s\n' % (_prefixedPath(bootEntry.kernel_filepath), kernelCmdLine)
            buf += '  echo "Loading initial ramdisk ..."\n'
            buf += '  initrd %s\n' % (_prefixedPath(bootEntry.initrd_filepath))
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

    def _parseGrubCfgAuxOsList(self, buf):
        ret = []
        for m in re.finditer(r'menuentry "Auxillary: (.*?)" {\n  search --fs-uuid --no-floppy --set (\S+)\n  chainloader +([0-9]+)\n}', buf):
            ret.append(HostAuxOs(m.group(1), m.group(2), m.group(3)))
        return ret


def _prefixedPathEfi(path):
    assert path.startswith("/boot/")
    return path[len("/boot"):]


def _prefixedPathBios(path):
    return path


def _grubRootDevCmd(devUuid):
    if devUuid.startswith("lvm/"):
        return "set root=(%s)" % (devUuid)
    elif devUuid.startswith("UUID="):
        return "search --fs-uuid --no-floppy --set %s" % (devUuid.replace("UUID=", ""))
    else:
        assert False


class _InternalParseError(Exception):
    pass


# def _getBackgroundFileInfo(self):
#     for fn in glob.glob("/boot/background.*"):
#         fn = fn.replace("/boot", "")
#         if fn.endswith(".png"):
#             return (fn, "png")
#         elif fn.endswith(".jpg"):
#             return (fn, "jpg")
#     return None
