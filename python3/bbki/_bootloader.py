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
import grub_install
from ._util import Util
from ._po import BootMode
from ._po import HostAuxOs
from ._boot_entry import BootEntryUtils
from ._exception import BootloaderInstallError


class BootLoader:

    STATUS_NORMAL = 1
    STATUS_NOT_VALID = 2
    STATUS_NOT_INSTALLED = 3

    def __init__(self, bbki, rootfs_mount_point, boot_mount_point):
        self._bbki = bbki
        self._rootfsMnt = rootfs_mount_point
        self._bootMnt = boot_mount_point

        self._grubCfgFile = os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "grub.cfg")
        self._grubEnvFile = os.path.join(self._bbki._fsLayout.get_boot_grub_dir(), "grubenv")

        self._targetObj = grub_install.Target(grub_install.TargetType.MOUNTED_HDD_DEV, grub_install.TargetAccessMode.RW,
                                              rootfs_mount_point=self._rootfsMnt, boot_mount_point=self._bootMnt)

        if self._targetObj.get_platform_install_info(grub_install.PlatformType.X86_64_EFI).status != grub_install.PlatformInstallInfo.Status.NOT_INSTALLED:
            bootMode = BootMode.EFI
            pt = grub_install.PlatformType.X86_64_EFI
        elif self._targetObj.get_platform_install_info(grub_install.PlatformType.I386_PC).status != grub_install.PlatformInstallInfo.Status.NOT_INSTALLED:
            bootMode = BootMode.BIOS
            pt = grub_install.PlatformType.I386_PC
        else:
            self._status = self.STATUS_NOT_INSTALLED
            self._bootMode = None
            self._mainBootPostfix = None
            self._kernelCmdLine = None
            self._invalidReason = None
            return

        if self._targetObj.get_platform_install_info(pt).status == grub_install.PlatformInstallInfo.Status.NOT_VALID:
            self._status = self.STATUS_NOT_VALID
            self._bootMode = None
            self._mainBootPostfix = None
            self._kernelCmdLine = None
            self._invalidReason = self._targetObj.get_platform_install_info(pt).reason
            return

        assert self._targetObj.get_platform_install_info(pt).status == grub_install.PlatformInstallInfo.Status.NORMAL
        ret = None
        try:
            ret = self._checkAndParseGrubCfg(bootMode)
        except _InternalParseError as e:
            self._status = self.STATUS_NOT_VALID
            self._bootMode = None
            self._mainBootPostfix = None
            self._kernelCmdLine = None
            self._invalidReason = str(e)
            return

        self._status = self.STATUS_NORMAL
        self._bootMode = bootMode
        self._mainBootPostfix = ret[0]
        self._kernelCmdLine = ret[1]
        self._invalidReason = None
        return

    def getStatus(self):
        return self._status

    def getInvalidReason(self):
        assert self._status == self.STATUS_NOT_VALID
        return self._invalidReason

    def getBootMode(self):
        assert self._status == self.STATUS_NORMAL
        return self._bootMode

    def getFilepaths(self):
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

    def install(self, boot_mode, rootfs_mnt, esp_mnt, main_boot_entry, aux_os_list, aux_kernel_init_cmdline):
        assert rootfs_mnt == self._rootfsMnt and esp_mnt == self._bootMnt
        assert main_boot_entry.has_kernel_files() and main_boot_entry.has_initrd_files()
        assert not main_boot_entry.is_historical()

        # generate grub.cfg
        # may raise exception
        kernelCmdLine = self._getKernelCmdLine(aux_kernel_init_cmdline)
        buf = self._genGrubCfg(boot_mode, main_boot_entry, aux_os_list, kernelCmdLine)

        # remove if needed
        if self._status == self.STATUS_NORMAL:
            self.remove()
        elif self._status == self.STATUS_NOT_VALID:
            self.remove(bForce=True)
        elif self._status == self.STATUS_NOT_INSTALLED:
            pass
        else:
            assert False

        # install grub files
        s = grub_install.Source("/")
        if boot_mode == BootMode.EFI:
            self._targetObj.install_platform(grub_install.PlatformType.X86_64_EFI, s, removable=True, update_nvram=False)
        elif boot_mode == BootMode.BIOS:
            self._targetObj.install_platform(grub_install.PlatformType.I386_PC, s)
        else:
            assert False
        self._targetObj.install_data_files(s, locales="*", fonts="*")

        # write grub.cfg file
        with open(self._grubCfgFile, "w") as f:
            f.write(buf)

        # record variable value
        self._status = self.STATUS_NORMAL
        self._bootMode = boot_mode
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
        buf = self._genGrubCfg(self._bootMode, mainBootEntry, auxOsList, kernelCmdLine)

        # write grub.cfg file
        with open(self._grubCfgFile, "w") as f:
            f.write(buf)

        # update record variables
        self._mainBootPostfix = mainBootEntry.postfix
        self._kernelCmdLine = kernelCmdLine

    def remove(self, bForce=False):
        if self._status == self.STATUS_NORMAL:
            pass
        elif self._status == self.STATUS_NOT_VALID:
            if not bForce:
                raise ValueError("bootloader contains errors, please fix them manually")
        elif self._status == self.STATUS_NOT_INSTALLED:
            return

        self._targetObj.remove_all()

        self._status = self.STATUS_NOT_INSTALLED
        self._bootMode = None
        self._mainBootPostfix = None
        self._kernelCmdLine = None
        self._invalidReason = None

    def compare_source(self):
        assert self._status == self.STATUS_NORMAL
        self._targetObj.compare_source(grub_install.Source("/"))

    def _getKernelCmdLine(self, aux_kernel_init_cmdline):
        kernelCmdLine = ""
        kernelCmdLine += " console=ttynull"                                               # global data: only use console when debug boot process
        kernelCmdLine += " %s" % (aux_kernel_init_cmdline)                                # host level extra data
        kernelCmdLine += " %s" % (self._bbki.config.get_kernel_extra_init_cmdline())      # admin level extra data
        kernelCmdLine = kernelCmdLine.strip()
        return kernelCmdLine

    def _checkAndParseGrubCfg(self, boot_mode):
        if not os.path.exists(self._grubCfgFile):
            raise _InternalParseError("\"%s\" does not exist" % (self._grubCfgFile))
        if not Util.cmdCallTestSuccess("grub-script-check", self._grubCfgFile):
            raise _InternalParseError("\"%s\" is invalid" % (self._grubCfgFile))
        buf = pathlib.Path(self._grubCfgFile).read_text()

        m = re.search(r'#   rootfs device: (\S+)', buf, re.M)
        if m is None:
            raise _InternalParseError("no rootfs device UUID in \"%s\"" % (self._grubCfgFile))
        if not m.group(1).startswith("UUID="):
            raise _InternalParseError("invalid rootfs device UUID in \"%s\"" % (self._grubCfgFile))
        rootfsDevUuid = m.group(1).replace("UUID=", "")
        if Util.getBlkDevUuid(self._rootfsMnt.device) != rootfsDevUuid:
            raise _InternalParseError("rootfs device %s can not be found" % (rootfsDevUuid))

        if boot_mode == BootMode.EFI:
            m = re.search(r'#   ESP partition: (\S+)', buf, re.M)
            if m is None:
                raise _InternalParseError("no ESP partition UUID in \"%s\"" % (self._grubCfgFile))
            if not m.group(1).startswith("UUID="):
                raise _InternalParseError("invalid ESP partition UUID in \"%s\"" % (self._grubCfgFile))
            espDevUuid = m.group(1).replace("UUID=", "")
            if Util.getBlkDevUuid(self._bootMnt.device) != espDevUuid:
                raise _InternalParseError("ESP partition %s can not be found" % (espDevUuid))
        elif boot_mode == BootMode.BIOS:
            pass
        else:
            assert False

        m = re.search(r'menuentry "Stable: Linux-\S+" {\n.*?\n  linux \S*/kernel-(\S+) quiet (.*?)\n', buf, re.S)
        if m is None:
            raise _InternalParseError("no main boot entry in \"%s\"" % (self._grubCfgFile))
        return (m.group(1), m.group(2))

    def _genGrubCfg(self, bootMode, mainBootEntry, auxOsList, kernelCmdLine):
        buf = ''

        rootfsDevUuid = Util.getBlkDevUuid(self._rootfsMnt.device)
        if self._bootMnt is not None:
            espDevUuid = Util.getBlkDevUuid(self._bootMnt.device)
        else:
            espDevUuid = None

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
            buf += '  linux %s quiet %s\n' % (_prefixedPath(mainBootEntry.kernel_filepath), kernelCmdLine)
            buf += '  initrd %s\n' % (_prefixedPath(mainBootEntry.initrd_filepath))
            buf += '}\n'
            buf += '\n'

            # write menu entry for main kernel
            buf += 'menuentry "Current: Linux-%s" {\n' % (mainBootEntry.postfix)
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
            buf += '  linux %s dev_uuid=%s basedir=%s\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_kernel_filepath()),
                                                            grubRootDevUuid,
                                                            _prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_dir()))
            buf += '  initrd %s\n' % (_prefixedPath(self._bbki._fsLayout.get_boot_rescue_os_initrd_filepath()))
            buf += '}\n'
            buf += '\n'

        # write menu entry for auxillary os
        for auxOs in auxOsList:
            buf += 'menuentry "Auxillary: %s" {\n' % (auxOs.name)
            buf += '  search --fs-uuid --no-floppy --set %s\n' % (auxOs.partition_uuid.replace("UUID=", ""))    # aux-os is not in the same device as grub.cfg is
            buf += '  chainloader +%d\n' % (auxOs.chainloader_number)
            buf += '}\n'
            buf += '\n'

        # write menu entry for history kernels
        for bootEntry in self._bbki.get_history_boot_entries():
            buf += 'menuentry "History: Linux-%s" {\n' % (bootEntry.postfix)
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
