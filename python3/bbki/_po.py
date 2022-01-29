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
from ._exception import RunningEnvironmentError


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

    def __eq__(self, other):
        ret = (type(self) == type(other) and self.name == other.name)
        if ret:
            assert self.cmd == other.cmd
        return ret

    def __hash__(self):
        return hash(self.name)


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
                self.boot_disk_id = Util.getDiskId(self.boot_disk_path)
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
    FS_TYPE_EXT4 = "ext4"
    FS_TYPE_BTRFS = "btrfs"
    FS_TYPE_BCACHEFS = "bcachefs"

    def __init__(self, name, mount_point, dev_path_or_uuid, fs_type=None, mnt_opt=None, underlay_disk=None):
        self.name = None
        self.mount_point = None
        self.dev_path = None
        self.dev_uuid = None
        self.fs_type = None
        self.mnt_opt = None
        self.underlay_disk = None

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

        # self.dev_path and self.dev_uuid, may contain multiple value seperated by ":"
        tlist = dev_path_or_uuid.split(":")
        if all([item.startswith("/dev/") for item in tlist]):
            self.dev_path = dev_path_or_uuid
            self.dev_uuid = ":".join([Util.getBlkDevUuid(item) for item in tlist])   # FS-UUID, not PART-UUID
        elif all([re.fullmatch("[A-Z0-9-]+", item) for item in tlist]):
            self.dev_path = None
            self.dev_uuid = dev_path_or_uuid
        else:
            assert False

        # self.fs_type
        if fs_type is not None:
            assert self.dev_path is None                                    # self.dev_path and parameter "fs_type" are mutally exclusive
            assert fs_type in [self.FS_TYPE_VFAT, self.FS_TYPE_EXT4, self.FS_TYPE_BTRFS, self.FS_TYPE_BCACHEFS]
            self.fs_type = fs_type
        else:
            assert self.dev_path is not None
            for item in self.dev_path.split(":"):
                t = Util.getBlkDevFsType(item)
                if self.fs_type is None:
                    self.fs_type = t
                else:
                    assert self.fs_type == t

        # FIXME: use PART-UUID for bcachefs until blkid supports it
        if self.fs_type == "bcachefs":
            if self.dev_path is not None:
                self.dev_uuid = ":".join([Util.getBlkDevPartUuid(item) for item in self.dev_path.split(":")])

        # self.mnt_opt
        if self.name == self.NAME_ROOT:
            if mnt_opt is not None:
                assert mnt_opt == ""
            else:
                mnt_opt = ""
        elif self.name == self.NAME_ESP:
            if mnt_opt is not None:
                assert mnt_opt == "ro,dmask=022,fmask=133"
            else:
                mnt_opt = "ro,dmask=022,fmask=133"
        else:
            assert isinstance(mnt_opt, str)
        self.mnt_opt = mnt_opt

        # self.underlay_disk
        if underlay_disk is not None:
            assert self.dev_path is None                                    # self.dev_path and parameter "underlay_disk" are mutally exclusive
            assert all([isinstance(x, HostDisk) for x in anytree.PostOrderIter(underlay_disk)])
            self.underlay_disk = underlay_disk
        else:
            assert self.dev_path is not None
            self.underlay_disk = HostDisk.getUnderlayDisk(self.dev_path, None)


class HostDisk(anytree.node.nodemixin.NodeMixin):

    def __init__(self, uuid, parent):
        super().__init__()
        self.parent = parent
        self.uuid = uuid

    def __eq__(self, other):
        return type(self) == type(other) and self.uuid == other.uuid

    def __hash__(self):
        return hash(self.uuid)

    @staticmethod
    def getUnderlayDisk(devPath, parent):
        klassList = [
            HostDiskBtrfs,
            HostDiskBcachefs,
            HostDiskLvmLv,
            HostDiskBcache,
            HostDiskPartition,
            HostDiskScsiDisk,
            HostDiskXenDisk,
            HostDiskVirtioDisk,
            HostDiskNvmeDisk,
        ]
        for klass in klassList:
            ret = klass.getUnderlayDisk(devPath, parent)
            if ret is not None:
                return ret

        # unknown
        raise RunningEnvironmentError("unknown device \"%s\"" % (devPath))


class HostDiskBtrfs(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: UUID of the whole btrfs filesystem
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        if Util.getBlkDevFsType(devPath) == "btrfs" and (parent is None or not isinstance(parent, cls)):
            bdi = cls(Util.btrfsGetUuid(devPath), parent)
            for slaveDevPath in Util.btrfsGetSlavePathList(devPath):
                HostDisk.getUnderlayDisk(slaveDevPath, bdi)
            return bdi
        return None


class HostDiskBcachefs(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: UUID of the whole bcachefs filesystem
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        if ":" in devPath or (Util.getBlkDevFsType(devPath) == "bcachefs" and (parent is None or not isinstance(parent, cls))):
            slaveDevPathList = devPath.split(":")
            bdi = cls(Util.bcachefsGetUuid(slaveDevPathList), parent)
            for slaveDevPath in slaveDevPathList:
                HostDisk.getUnderlayDisk(slaveDevPath, bdi)
            return bdi
        return None


class HostDiskLvmLv(HostDisk):

    def __init__(self, uuid, vg_name, lv_name, parent):
        # uuid: FS-UUID of the filesystem in LV??
        super().__init__(uuid, parent)
        self.vg_name = vg_name
        self.lv_name = lv_name

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        lvmInfo = Util.getBlkDevLvmInfo(devPath)
        if lvmInfo is not None:
            bdi = cls(Util.getBlkDevUuid(devPath), lvmInfo[0], lvmInfo[1], parent)
            for slaveDevPath in Util.lvmGetSlaveDevPathList(lvmInfo[0]):
                HostDisk.getUnderlayDisk(slaveDevPath, bdi)
            return bdi
        return None


class HostDiskBcache(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: FS-UUID of the filesystem in bcache device??
        super().__init__(uuid, parent)
        self.cache_dev_list = []
        self.backing_dev = None

    def add_cache_dev(self, disk):
        self.cache_dev_list.append(disk)

    def add_backing_dev(self, disk):
        assert self.backing_dev is None
        self.backing_dev = disk

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        m = re.fullmatch("/dev/bcache[0-9]+", devPath)
        if m is not None:
            bdi = cls(Util.getBlkDevUuid(devPath), parent)
            slist = Util.bcacheGetSlaveDevPathList(devPath)
            for i in range(0, len(slist)):
                if i < len(slist) - 1:
                    bdi.add_cache_dev(HostDisk.getUnderlayDisk(slist[i], bdi))
                else:
                    bdi.add_backing_dev(HostDisk.getUnderlayDisk(slist[i], bdi))
            return bdi
        return None


class HostDiskPartition(HostDisk):

    PART_TYPE_MBR = 1
    PART_TYPE_GPT = 2

    def __init__(self, uuid, part_type, parent):
        assert self.PART_TYPE_MBR <= part_type <= self.PART_TYPE_GPT

        # uuid: FS-UUID of the filesystem in this partition, no code is using this value
        super().__init__(uuid, parent)
        self.part_type = part_type

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        m = re.fullmatch("(/dev/sd[a-z])[0-9]+", devPath)
        if m is None:
            m = re.fullmatch("(/dev/xvd[a-z])[0-9]+", devPath)
            if m is None:
                m = re.fullmatch("(/dev/vd[a-z])[0-9]+", devPath)
                if m is None:
                    m = re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)p[0-9]+", devPath)
        if m is not None:
            m2 = re.search(r'[^| ]PTTYPE="(\S+)"', Util.cmdCall("blkid", m.group(1)), re.M)
            if m2.group(1) == "dos":
                ptType = cls.PART_TYPE_MBR
            elif m2.group(1) == "gpt":
                ptType = cls.PART_TYPE_GPT
            else:
                raise RunningEnvironmentError("unknown partition type \"%s\" for block device \"%s\"" % (m2.group(1), devPath))
            bdi = cls(Util.getBlkDevUuid(devPath), ptType, parent)
            HostDisk.getUnderlayDisk(m.group(1), bdi)
            return bdi
        return None


class HostDiskScsiDisk(HostDisk):

    def __init__(self, uuid, host_controller_name, parent):
        # uuid: I don't know what the value is, no code is using this value
        super().__init__(uuid, parent)
        self.host_controller_name = host_controller_name

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        m = re.fullmatch("/dev/sd[a-z]", devPath)
        if m is not None:
            return cls(Util.getBlkDevUuid(devPath), Util.scsiGetHostControllerName(devPath), parent)
        return None


class HostDiskNvmeDisk(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: I don't know what the value is, no code is using this value
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        m = re.fullmatch("/dev/nvme[0-9]+n[0-9]+", devPath)
        if m is not None:
            return cls(Util.getBlkDevUuid(devPath), parent)
        return None


class HostDiskXenDisk(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: I don't know what the value is, no code is using this value
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        m = re.fullmatch("/dev/xvd[a-z]", devPath)
        if m is not None:
            return cls(Util.getBlkDevUuid(devPath), parent)
        return None


class HostDiskVirtioDisk(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: I don't know what the value is, no code is using this value
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent):
        m = re.fullmatch("/dev/vd[a-z]", devPath)
        if m is not None:
            return cls(Util.getBlkDevUuid(devPath), parent)
        return None


class HostAuxOs:

    def __init__(self, name, partition_path_or_uuid, chainloader_number):
        self.name = name
        if partition_path_or_uuid.startswith("/dev/"):
            self.partition_path = partition_path_or_uuid
            self.partition_uuid = Util.getBlkDevUuid(self.partition_path)   # FS-UUID, not PART-UUID
        else:
            self.partition_path = None
            self.partition_uuid = partition_path_or_uuid
        self.chainloader_number = chainloader_number

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        if self.name != other.name:
            return False
        if self.partition_uuid != other.partition_uuid:
            return False
        if self.chainloader_number != other.chainloader_number:
            return False
        if self.partition_path is not None and other.partition_path is not None:
            assert self.partition_path == other.partition_path
        return True

    def __hash__(self):
        return hash((self.name, self.partition_uuid, self.chainloader_number))


class FsLayout:

    def __init__(self, bbki):
        self._bbki = bbki

    def get_boot_dir(self):
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
