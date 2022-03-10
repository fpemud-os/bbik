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
from ._util import PhysicalDiskMounts
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

    def __init__(self, boot_mode, mount_points):
        self.mount_points = None

        # self.mount_points
        if boot_mode == BootMode.EFI:
            assert len(mount_points) >= 2
            assert mount_points[0].mount_point == "/"
            assert len([x for x in mount_points if x.mount_point == "/"]) == 1
            assert len([x for x in mount_points if x.mount_point == "/boot"]) == 1
        elif boot_mode == BootMode.BIOS:
            assert mount_points[0].mount_point == "/"
            assert len([x for x in mount_points if x.mount_point == "/"]) == 1
            assert all([x.dev_path is not None for x in mount_points])
        else:
            assert False
        self.mount_points = mount_points

    def get_root_mount_point(self):
        for m in self.mount_points:
            if m.mount_point == "/":
                return m
        assert False

    def get_esp_mount_point(self):
        for m in self.mount_points:
            if m.mount_point == "/boot":
                return m
        assert False

    def get_other_mount_points(self):
        ret = []
        for m in self.mount_points:
            if m.mount_point not in ["/", "/boot"]:
                ret.append(m)
        return ret


class HostMountPoint:

    FS_TYPE_VFAT = "vfat"
    FS_TYPE_EXT4 = "ext4"
    FS_TYPE_BTRFS = "btrfs"
    FS_TYPE_BCACHEFS = "bcachefs"

    def __init__(self, mount_point, dev_path_or_uuid, fs_type=None, mnt_opts=None, underlay_disk=None):
        self.mount_point = None
        self.dev_path = None
        self.dev_uuid = None
        self.fs_type = None
        self.mnt_opts = None
        self.underlay_disk = None

        # self.mount_point
        assert os.path.isabs(mount_point)
        self.mount_point = mount_point

        # self.dev_path and self.dev_uuid, may contain multiple values seperated by ":"
        if ":" not in dev_path_or_uuid:
            if dev_path_or_uuid.startswith("/dev/"):
                self.dev_path = dev_path_or_uuid
                self.dev_uuid = "UUID=%s" % (Util.getBlkDevUuid(dev_path_or_uuid))
            elif re.fullmatch(r'UUID=\S+', dev_path_or_uuid):
                self.dev_path = None
                self.dev_uuid = dev_path_or_uuid
            else:
                assert False
        else:
            tlist = dev_path_or_uuid.split(":")
            if all([item.startswith("/dev/") for item in tlist]):
                self.dev_path = dev_path_or_uuid
                self.dev_uuid = ":".join(["UUID_SUB=%s" % (Util.getBlkDevSubUuid(item)) for item in tlist])
            elif all([re.fullmatch(r'UUID_SUB=\S+', item) for item in tlist]):
                self.dev_path = None
                self.dev_uuid = dev_path_or_uuid
            else:
                assert False

        # self.fs_type
        if self.dev_path is not None:
            assert fs_type is None                                     # self.dev_path and parameter "fs_type" are mutally exclusive
            for item in self.dev_path.split(":"):
                t = Util.getBlkDevFsType(item)
                if self.fs_type is None:
                    self.fs_type = t
                else:
                    assert self.fs_type == t
        else:
            assert fs_type in [self.FS_TYPE_VFAT, self.FS_TYPE_EXT4, self.FS_TYPE_BTRFS, self.FS_TYPE_BCACHEFS]
            self.fs_type = fs_type

        # self.mnt_opts
        if self.dev_path is not None:
            assert mnt_opts is None                                    # self.dev_path and parameter "mnt_opts" are mutally exclusive
            self.mnt_opts = PhysicalDiskMounts.find_entry_by_mount_point(self.mount_point).mnt_opts
        else:
            assert isinstance(mnt_opts, str)
            self.mnt_opts = mnt_opts

        # self.underlay_disk
        if self.dev_path is not None:
            assert underlay_disk is None                               # self.dev_path and parameter "underlay_disk" are mutally exclusive
            self.underlay_disk = HostDisk.getUnderlayDisk(self.dev_path, mount_point=self.mount_point)
        else:
            assert underlay_disk is not None
            assert all([isinstance(x, HostDisk) for x in anytree.PostOrderIter(underlay_disk)])
            self.underlay_disk = underlay_disk


class HostDisk(anytree.node.nodemixin.NodeMixin):

    def __init__(self, uuid, parent):
        assert re.fullmatch(r'(UUID=|UUID_SUB=)\S+', uuid)
        super().__init__()
        self.parent = parent
        self.uuid = uuid

    def __eq__(self, other):
        return type(self) == type(other) and self.uuid == other.uuid

    def __hash__(self):
        return hash(self.uuid)

    @staticmethod
    def getUnderlayDisk(devPath, parent=None, mount_point=None):
        if parent is None:
            assert mount_point is not None
        else:
            assert mount_point is None

        klassList = [
            HostDiskBtrfsRaid,
            HostDiskBcachefsRaid,
            HostDiskLvmLv,
            HostDiskBcache,
            HostDiskScsiHdd,
            HostDiskXenHdd,
            HostDiskVirtioHdd,
            HostDiskNvmeHdd,
        ]
        for klass in klassList:
            ret = klass.getUnderlayDisk(devPath, parent, mount_point)
            if ret is not None:
                return ret

        # unknown
        raise RunningEnvironmentError("unknown device \"%s\"" % (devPath))

    @staticmethod
    def _getSubUuidOrUuidWithPrefix(devPath):
        ret = Util.getBlkDevSubUuid(devPath)
        if ret is not None:
            return "UUID_SUB=" + ret
        ret = Util.getBlkDevUuid(devPath)
        if ret is not None:
            return "UUID=" + ret
        assert False


class HostDiskWholeDiskOrPartition(HostDisk):

    WHOLE_DISK = 1
    MBR_PARTITION = 2
    GPT_PARTITION = 3

    def __init__(self, uuid, partition_type, parent):
        super().__init__(uuid, parent)
        assert partition_type in [self.WHOLE_DISK, self.MBR_PARTITION, self.GPT_PARTITION]
        self.partition_type = partition_type

    @classmethod
    def _getPartitionType(cls, diskDevPath, partitionId):
        if partitionId is None:
            return cls.WHOLE_DISK
        else:
            m2 = re.search(r'(^| )PTTYPE="(\S+)"', Util.cmdCall("blkid", diskDevPath), re.M)
            if m2.group(2) == "dos":
                return cls.MBR_PARTITION
            elif m2.group(2) == "gpt":
                return cls.GPT_PARTITION
            else:
                raise RunningEnvironmentError("unknown partition type \"%s\" for block device \"%s\"" % (m2.group(2), diskDevPath))


class HostDiskBtrfsRaid(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: FS-UUID of the whole btrfs filesystem
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        if os.path.exists(devPath):
            if parent is None and Util.getBlkDevFsType(devPath) == "btrfs":
                bdi = cls("UUID=" + Util.btrfsGetUuid(mountPoint), parent)
                for slaveDevPath in Util.btrfsGetSlavePathList(mountPoint):
                    HostDisk.getUnderlayDisk(slaveDevPath, parent=bdi)
                return bdi
        return None


class HostDiskBcachefsRaid(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: FS-UUID of the whole bcachefs filesystem
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        if mountPoint is not None:
            slaveDevPathList = devPath.split(":")
            if len(slaveDevPathList) > 1:
                if any([Util.getBlkDevFsType(x) == "bcachefs" for x in slaveDevPathList]):
                    assert all([Util.getBlkDevFsType(x) == "btrfs" for x in slaveDevPathList])
                    bdi = cls("UUID=" + Util.bcachefsGetUuid(slaveDevPathList), parent)
                    for slaveDevPath in slaveDevPathList:
                        HostDisk.getUnderlayDisk(slaveDevPath, parent=bdi)
                    return bdi
        return None


class HostDiskLvmLv(HostDisk):

    def __init__(self, uuid, vg_name, lv_name, parent):
        # uuid: FS-UUID of the filesystem in this LV, or SUB-UUID takes priority for multi-volume filesystem
        super().__init__(uuid, parent)
        self.vg_name = vg_name
        self.lv_name = lv_name

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        lvmInfo = Util.getBlkDevLvmInfo(devPath)
        if lvmInfo is not None:
            assert mountPoint is not None
            bdi = cls(cls._getSubUuidOrUuidWithPrefix(devPath), lvmInfo[0], lvmInfo[1], parent)
            for slaveDevPath in Util.lvmGetSlaveDevPathList(lvmInfo[0]):
                HostDisk.getUnderlayDisk(slaveDevPath, parent=bdi)
            return bdi
        return None


class HostDiskBcache(HostDisk):

    def __init__(self, uuid, parent):
        # uuid: FS-UUID of the filesystem in this bcache device, or SUB-UUID takes priority for multi-volume filesystem
        super().__init__(uuid, parent)
        self.cache_dev_list = []
        self.backing_dev = None

    def add_cache_dev(self, disk):
        self.cache_dev_list.append(disk)

    def add_backing_dev(self, disk):
        assert self.backing_dev is None
        self.backing_dev = disk

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        m = re.fullmatch("/dev/bcache[0-9]+", devPath)
        if m is not None:
            bdi = cls(cls._getSubUuidOrUuidWithPrefix(devPath), parent)
            slist = Util.bcacheGetSlaveDevPathList(devPath)
            for i in range(0, len(slist)):
                if i < len(slist) - 1:
                    bdi.add_cache_dev(HostDisk.getUnderlayDisk(slist[i], parent=bdi))
                else:
                    bdi.add_backing_dev(HostDisk.getUnderlayDisk(slist[i], parent=bdi))
            return bdi
        return None


class HostDiskScsiHdd(HostDiskWholeDiskOrPartition):

    def __init__(self, uuid, partition_type, host_controller_name, parent):
        # uuid: FS-UUID of the filesystem in this bcache device, or SUB-UUID takes priority for multi-volume filesystem
        super().__init__(uuid, partition_type, parent)
        self.host_controller_name = host_controller_name

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        m = re.fullmatch("(/dev/sd[a-z])([0-9]+)?", devPath)
        if m is not None:
            ptype = cls._getPartitionType(m.group(1), m.group(2))
            return cls(cls._getSubUuidOrUuidWithPrefix(devPath), ptype, Util.scsiGetHostControllerName(m.group(1)), parent)
        return None


class HostDiskNvmeHdd(HostDiskWholeDiskOrPartition):

    def __init__(self, uuid, partition_type, parent):
        # uuid: FS-UUID of the filesystem in this bcache device, or SUB-UUID takes priority for multi-volume filesystem
        super().__init__(uuid, partition_type, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        m = re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)(p([0-9]+))?", devPath)
        if m is not None:
            ptype = cls._getPartitionType(m.group(1), m.group(3))
            return cls(cls._getSubUuidOrUuidWithPrefix(devPath), ptype, parent)
        return None


class HostDiskXenHdd(HostDiskWholeDiskOrPartition):

    def __init__(self, uuid, partition_type, parent):
        # uuid: FS-UUID of the filesystem in this bcache device, or SUB-UUID takes priority for multi-volume filesystem
        super().__init__(uuid, partition_type, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        m = re.fullmatch("(/dev/xvd[a-z])([0-9]+)?", devPath)
        if m is not None:
            ptype = cls._getPartitionType(m.group(1), m.group(2))
            return cls(cls._getSubUuidOrUuidWithPrefix(devPath), ptype, parent)
        return None


class HostDiskVirtioHdd(HostDiskWholeDiskOrPartition):

    def __init__(self, uuid, parent):
        # uuid: FS-UUID of the filesystem in this bcache device, or SUB-UUID takes priority for multi-volume filesystem
        super().__init__(uuid, parent)

    @classmethod
    def getUnderlayDisk(cls, devPath, parent, mountPoint):
        m = re.fullmatch("(/dev/vd[a-z])([0-9]+)?", devPath)
        if m is not None:
            ptype = cls._getPartitionType(m.group(1), m.group(2))
            return cls(cls._getSubUuidOrUuidWithPrefix(devPath), ptype, parent)
        return None


class HostAuxOs:

    def __init__(self, name, partition_path_or_uuid, chainloader_number):
        self.name = name
        if partition_path_or_uuid.startswith("/dev/"):
            self.partition_path = partition_path_or_uuid
            self.partition_uuid = "UUID=" + Util.getBlkDevUuid(self.partition_path)
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
