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
import anytree
from ._util import Util


class KernelType:

    LINUX = "linux"


class BootMode:

    EFI = "efi"
    BIOS = "bios"


class SystemInit:

    TYPE_SYSVINIT = "sysv-init"
    TYPE_OPENRC = "openrc"
    TYPE_SYSTEMD = "systemd"
    TYPE_CUSTOM = "custom"

    def __init__(self, name, cmd):
        assert name in [self.TYPE_SYSVINIT, self.TYPE_OPENRC, self.TYPE_SYSTEMD, self.TYPE_CUSTOM]
        self.name = name
        self.cmd = cmd


class RescueOsSpec:

    def __init__(self, bbki):
        self.root_dir = bbki._fsLayout.get_boot_rescue_os_dir()
        self.kernel_filepath = bbki._fsLayout.get_boot_rescue_os_kernel_filepath()
        self.initrd_filepath = bbki._fsLayout.get_boot_rescue_os_initrd_filepath()


class HostStorage:

    def __init__(self, boot_mode, mount_points, boot_disk_path_or_id=None):
        self.mount_points = None
        self.boot_disk_path = None
        self.boot_disk_id = None

        # self.mount_points
        if boot_mode == BootMode.EFI:
            assert len(mount_points) >= 2
            assert mount_points[0].name == HostMountPoint.NAME_ROOT
            assert mount_points[1].name == HostMountPoint.NAME_ESP
            assert len([x for x in mount_points if x.name == HostMountPoint.NAME_ROOT]) == 1
            assert len([x for x in mount_points if x.name == HostMountPoint.NAME_ESP]) == 1
        elif boot_mode == BootMode.BIOS:
            assert mount_points[0].name == HostMountPoint.NAME_ROOT
            assert len([x for x in mount_points if x.name == HostMountPoint.NAME_ROOT]) == 1
            assert len([x for x in mount_points if x.name == HostMountPoint.NAME_ESP]) == 0
            assert all([x.dev_path is not None for x in mount_points])
        else:
            assert False
        self.mount_points = mount_points

        # self.boot_disk_path and self.boot_disk_id
        if boot_mode == BootMode.EFI:
            assert boot_disk_path_or_id is None
        elif boot_mode == BootMode.BIOS:
            if boot_disk_path_or_id.startswith("/dev/"):
                self.boot_disk_path = boot_disk_path_or_id
                self.boot_disk_id = Util.getDiskById(self.boot_disk_path)
            else:
                self.boot_disk_path = None
                self.boot_disk_id = boot_disk_path_or_id
        else:
            assert False

    def get_root_mount_point(self):
        for m in self.mount_points:
            if m.name == HostMountPoint.NAME_ROOT:
                return m
        assert False

    def get_esp_mount_point(self):
        for m in self.mount_points:
            if m.name == HostMountPoint.NAME_ESP:
                return m
        assert False

    def get_other_mount_points(self):
        ret = []
        for m in self.mount_points:
            if m.name not in [HostMountPoint.NAME_ROOT, HostMountPoint.NAME_ESP]:
                ret.append(m)
        return ret


class HostMountPoint:

    NAME_ROOT = "root"
    NAME_ESP = "boot"

    FS_TYPE_VFAT = "vfat"
    FS_TYPE_EXT4 = "ext4"           # deprecated
    FS_TYPE_BTRFS = "btrfs"

    def __init__(self, name, mount_point, dev_path_or_uuid, fs_type=None, mnt_opt=None, underlay_disks=None):
        self.name = None
        self.mount_point = None
        self.dev_path = None
        self.dev_uuid = None
        self.fs_type = None
        self.mnt_opt = None
        self.underlay_disks = None

        # self.name
        assert isinstance(name, str)
        self.name = name

        # self.mount_point
        assert os.path.isabs(mount_point)
        if self.name == self.NAME_ROOT:
            assert mount_point == "/"
        if self.name == self.NAME_ESP:
            assert mount_point == "/boot"
        self.mount_point = mount_point

        # self.dev_path and self.dev_uuid
        if dev_path_or_uuid.startswith("/dev/"):
            self.dev_path = dev_path_or_uuid
            self.dev_uuid = Util.getBlkDevUuid(self.dev_path)               # FS-UUID, not PART-UUID
        else:
            self.dev_path = None
            self.dev_uuid = dev_path_or_uuid

        # self.fs_type
        if fs_type is not None:
            assert self.dev_path is None                                    # self.dev_path and parameter "fs_type" are mutally exclusive
            assert fs_type in [self.FS_TYPE_VFAT, self.FS_TYPE_EXT4, self.FS_TYPE_BTRFS]
            self.fs_type = fs_type
        else:
            assert self.dev_path is not None
            self.fs_type = Util.getBlkDevFsType(self.dev_path)

        # self.mnt_opt
        if mnt_opt is not None:
            assert self.dev_path is None                                    # self.dev_path and parameter "mnt_opt" are mutally exclusive
            assert isinstance(mnt_opt, str)
            self.mnt_opt = mnt_opt
        else:
            assert self.dev_path is not None
            self.mnt_opt = ""                                               # FIXME

        # self.underlay_disks
        if underlay_disks is not None:
            assert self.dev_path is None                                    # self.dev_path and parameter "underlay_disks" are mutally exclusive
            assert all([isinstance(x, HostDisk) for x in underlay_disks])
            self.underlay_disks = underlay_disks
        else:
            assert self.dev_path is not None
            self.underlay_disks = _getUnderlayDisks(self.dev_path)


class HostDisk(anytree.node.nodemixin.NodeMixin):

    def __init__(self, uuid, parent):
        super().__init__()
        self.parent = parent
        self.uuid = uuid

    def ___eq___(self, other):
        return type(self) == type(other) and self.uuid == other.uuid


class HostDiskLvmLv(HostDisk):

    def __init__(self, uuid, vg_name, lv_name, parent=None):
        super().__init__(uuid, parent)
        self.vg_name = vg_name
        self.lv_name = lv_name


class HostDiskBcache(HostDisk):

    def __init__(self, uuid, parent=None):
        super().__init__(uuid, parent)
        self.cache_dev_list = []
        self.backing_dev = None

    def add_cache_dev(self, disk):
        self.cache_dev_list.append(disk)

    def add_backing_dev(self, disk):
        assert self.backing_dev is None
        self.backing_dev = disk


class HostDiskScsiDisk(HostDisk):

    def __init__(self, uuid, host_controller_name, parent=None):
        super().__init__(uuid, parent)
        self.host_controller_name = host_controller_name


class HostDiskNvmeDisk(HostDisk):

    def __init__(self, uuid, parent=None):
        super().__init__(uuid, parent)


class HostDiskXenDisk(HostDisk):

    def __init__(self, uuid, parent=None):
        super().__init__(uuid, parent)


class HostDiskVirtioDisk(HostDisk):

    def __init__(self, uuid, parent=None):
        super().__init__(uuid, parent)


class HostDiskPartition(HostDisk):

    PART_TYPE_MBR = 1
    PART_TYPE_GPT = 2

    def __init__(self, uuid, part_type, parent=None):
        assert self.PART_TYPE_MBR <= part_type <= self.PART_TYPE_GPT

        super().__init__(uuid, parent)
        self.part_type = part_type


class HostAuxOs:

    def __init__(self, name, partition_path, partition_uuid, chainloader_number):
        self.name = name
        self.partition_path = partition_path
        self.partition_uuid = partition_uuid
        self.chainloader_number = chainloader_number


class FsLayout:

    def __init__(self, bbki):
        self._bbki = bbki

    def get_boot_dir(self):
        return "/boot"

    def get_lib_dir(self):
        return "/boot"

    def get_boot_history_dir(self):
        return "/boot/history"

    def get_boot_grub_dir(self):
        return "/boot/grub"

    def get_boot_grub_efi_dir(self):
        return "/boot/EFI"

    def get_boot_rescue_os_dir(self):
        return "/boot/rescue"

    def get_boot_rescue_os_kernel_filepath(self):
        return "/boot/rescue/vmlinuz"

    def get_boot_rescue_os_initrd_filepath(self):
        return "/boot/rescue/initrd.img"

    def get_kernel_modules_dir(self, kernel_verstr=None):
        if kernel_verstr is None:
            return "/lib/modules"
        else:
            return "/lib/modules/%s" % (kernel_verstr)

    def get_firmware_dir(self):
        return "/lib/firmware"


def _getUnderlayDisks(devPath, parent=None):
    # HostDiskLvmLv
    lvmInfo = Util.getBlkDevLvmInfo(devPath)
    if lvmInfo is not None:
        bdi = HostDiskLvmLv(Util.getBlkDevUuid(devPath), lvmInfo[0], lvmInfo[1], parent=parent)
        for slaveDevPath in Util.lvmGetSlaveDevPathList(lvmInfo[0]):
            _getUnderlayDisks(slaveDevPath, parent=bdi)
        return bdi

    # HostDiskPartition
    m = re.fullmatch("(/dev/sd[a-z])[0-9]+", devPath)
    if m is None:
        m = re.fullmatch("(/dev/xvd[a-z])[0-9]+", devPath)
        if m is None:
            m = re.fullmatch("(/dev/vd[a-z])[0-9]+", devPath)
            if m is None:
                m = re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)p[0-9]+", devPath)
    if m is not None:
        bdi = HostDiskPartition(Util.getBlkDevUuid(devPath), HostDiskPartition.PART_TYPE_MBR, parent=parent)        # FIXME: currently there's no difference when processing mbr and gpt partition
        _getUnderlayDisks(m.group(1), parent=bdi)
        return bdi

    # HostDiskScsiDisk
    m = re.fullmatch("/dev/sd[a-z]", devPath)
    if m is not None:
        return HostDiskScsiDisk(Util.getBlkDevUuid(devPath), Util.scsiGetHostControllerName(devPath), parent=parent)

    # HostDiskXenDisk
    m = re.fullmatch("/dev/xvd[a-z]", devPath)
    if m is not None:
        return HostDiskXenDisk(Util.getBlkDevUuid(devPath), parent=parent)

    # HostDiskVirtioDisk
    m = re.fullmatch("/dev/vd[a-z]", devPath)
    if m is not None:
        return HostDiskVirtioDisk(Util.getBlkDevUuid(devPath), parent=parent)

    # HostDiskNvmeDisk
    m = re.fullmatch("/dev/nvme[0-9]+n[0-9]+", devPath)
    if m is not None:
        return HostDiskNvmeDisk(Util.getBlkDevUuid(devPath), parent=parent)

    # bcache
    m = re.fullmatch("/dev/bcache[0-9]+", devPath)
    if m is not None:
        bdi = HostDiskBcache(Util.getBlkDevUuid(devPath))
        slist = Util.bcacheGetSlaveDevPathList(devPath)
        for i in range(0, len(slist)):
            if i < len(slist) - 1:
                bdi.add_cache_dev(_getUnderlayDisks(slist[i], parent=bdi))
            else:
                bdi.add_backing_dev(_getUnderlayDisks(slist[i], parent=bdi))
        return bdi

    # unknown
    assert False
