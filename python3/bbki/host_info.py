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
from .bbki import Bbki
from .util import Util


class HostInfo:

    MOUNT_TYPE_ROOT = 1
    MOUNT_TYPE_BOOT = 2
    MOUNT_TYPE_OTHER = 3

    def __init__(self, arch, boot_mode, boot_disk, mount_point_list):
        self.arch = None
        self.boot_mode = None
        self.boot_disk = None
        self.mount_point_list = None

        # self.arch
        if arch == "native":
            self.arch = os.uname().machine
        else:
            assert Util.isValidKernelArch(arch)
            self.arch = arch

        # self.boot_mode
        if boot_mode == "native":
            if Util.isEfi():
                boot_mode = Bbki.BOOT_MODE_EFI
            else:
                boot_mode = Bbki.BOOT_MODE_BIOS
        else:
            assert boot_mode in [Bbki.BOOT_MODE_EFI, Bbki.BOOT_MODE_BIOS]
            self.boot_mode = boot_mode

        # self.boot_disk
        self.boot_disk = boot_disk

        # self.mount_point_list
        if mount_point_list is not None:
            if boot_mode == Bbki.BOOT_MODE_EFI:
                assert len([x for x in mount_point_list if x.mount_type == HostMountPoint.MOUNT_TYPE_ROOT]) == 1
                ret = [x for x in mount_point_list if x.mount_type == HostMountPoint.MOUNT_TYPE_BOOT]
                assert len(ret) == 1
                assert self.boot_disk == Util.devPathPartitionToDisk(ret[0])
            elif boot_mode == Bbki.BOOT_MODE_BIOS:
                assert len([x for x in mount_point_list if x.mount_type == HostMountPoint.MOUNT_TYPE_ROOT]) == 1
                assert len([x for x in mount_point_list if x.mount_type == HostMountPoint.MOUNT_TYPE_BOOT]) == 0
                assert self.boot_disk is not None
            else:
                assert False
            self.mount_point_list = mount_point_list
        else:
            assert self.boot_disk is None


class HostMountPoint:

    def __init__(self, mount_type, mount_point, dev_path, fs_type, mount_option="", disk_stack=[]):
        assert HostInfo.MOUNT_TYPE_ROOT <= mount_type <= HostInfo.MOUNT_TYPE_OTHER
        assert Util.isValidFsType(fs_type)

        self.mount_type = mount_type
        self.mount_point = mount_point
        self.dev_path = dev_path
        self.fs_type = fs_type
        self.mount_option = ""              # FIXME
        self.disk_stack = disk_stack


class HostDiskStackNode(anytree.node.nodemixin.NodeMixin):

    def __init__(self, dev_path, parent=None):
        super().__init__(parent=parent)
        self.dev_path = dev_path


class HostDiskStackNodeLvmLv(HostDiskStackNode):

    def __init__(self, dev_path, vg_name, lv_name, parent=None):
        super().__init__(dev_path, parent=parent)
        self.vg_name = vg_name
        self.lv_name = lv_name


class HostDiskStackNodeBcache(HostDiskStackNode):

    def __init__(self, dev_path, cache_dev_list, backing_dev, parent=None):
        super().__init__(dev_path, parent=parent)
        self.cache_dev_list = cache_dev_list
        self.backing_dev = backing_dev


class HostDiskStackNodeHarddisk(HostDiskStackNode):

    DEV_TYPE_SCSI = 1
    DEV_TYPE_NVME = 2
    DEV_TYPE_XEN = 3
    DEV_TYPE_VIRTIO = 4

    def __init__(self, dev_path, dev_type, parent=None):
        assert self.DEV_TYPE_SCSI <= dev_type <= self.DEV_TYPE_VIRTIO
        super().__init__(dev_path, parent=parent)

        if re.fullmatch("/dev/sd[a-z]", dev_path):
            self.dev_type = self.DEV_TYPE_SCSI
        if re.fullmatch("/dev/xvd[a-z]", dev_path):
            self.dev_type = self.DEV_TYPE_XEN
        if re.fullmatch("/dev/vd[a-z]", dev_path):
            self.dev_type = self.DEV_TYPE_VIRTIO
        if re.fullmatch("/dev/nvme[0-9]+n[0-9]+", dev_path):
            self.dev_type = self.DEV_TYPE_NVME
        raise ValueError("unknown block device type")


class HostDiskStackNodePartition(HostDiskStackNode):

    PART_TYPE_MBR = 1
    PART_TYPE_GPT = 2

    def __init__(self, dev_path, part_type, parent=None):
        assert self.PART_TYPE_MBR <= part_type <= self.PART_TYPE_GPT
        super().__init__(dev_path, parent=parent)
        self.part_type = part_type


# FIXME:
class BlkDevInfo:

    def __init__(self):
        self.devPath = None               # str
        self.devType = None               # enum, "scsi_disk", "virtio_disk", "xen_disk", "nvme_disk", "lvm2_raid", "bcache_raid", "mbr_partition", "gpt_partition"
        self.fsType = None                # enum, "", "lvm2_member", "bcache", "ext4", "btrfs", "vfat"
        self.param = dict()





# def get_disk_stack(self):
#     ret = []
#     ret.append(DiskStackNodeLvmLv(util.rootLvDevPath, util.vgName, util.rootLvName))
#     if self._bSwapLv:
#         ret.append(DiskStackNodeLvmLv(util.swapLvDevPath, util.vgName, util.swapLvName))

#     for node in ret:
#         for d in self._diskList:
#             partNode = DiskStackNodePartition(util.devPathDiskToPartition(d, 1), DiskStackNodePartition.PART_TYPE_MBR, parent=node)
#             DiskStackNodeHarddisk(d, parent=partNode)

#     return ret


# def get_disk_stack(self):
#     partNode = DiskStackNodePartition(self._hddRootParti, DiskStackNodePartition.PART_TYPE_MBR)
#     DiskStackNodeHarddisk(self._hdd, parent=partNode)
#     return [partNode]



# def get_disk_stack(self):
#     ret = []

#     if True:
#         rootNode = DiskStackNodeLvmLv(util.rootLvDevPath, util.vgName, util.rootLvName)
#         for hddDev, bcacheDev in self._hddDict.items():
#             ssdPartList = [self._ssd] if self._ssdCacheParti is not None else []
#             bcacheNode = DiskStackNodeBcache(bcacheDev, ssdPartList, util.devPathDiskToPartition(hddDev, 1), parent=rootNode)
#             for s in ssdPartList:
#                 partNode = DiskStackNodePartition(s, DiskStackNodePartition.PART_TYPE_GPT, parent=bcacheNode)
#                 DiskStackNodeHarddisk(self._ssd, parent=partNode)
#         ret.append(rootNode)

#     for hddDev, bcacheDev in self._hddDict.items():
#         espNode = DiskStackNodePartition(util.devPathDiskToPartition(hddDev, 1), DiskStackNodePartition.PART_TYPE_GPT)
#         DiskStackNodeHarddisk(hddDev, parent=espNode)
#         ret.append(espNode)

#     if self._ssdEspParti is not None:
#         ssdEspNode = DiskStackNodePartition(self._ssdEspParti, DiskStackNodePartition.PART_TYPE_GPT)
#         DiskStackNodeHarddisk(self._ssd, parent=ssdEspNode)
#         ret.append(ssdEspNode)

#     if self._ssdSwapParti is not None:
#         swapNode = DiskStackNodePartition(self._ssdSwapParti, DiskStackNodePartition.PART_TYPE_GPT, parent=bcacheNode)
#         DiskStackNodeHarddisk(self._ssd, parent=swapNode)
#         ret.append(swapNode)

#     return ret



# def get_disk_stack(self):
#     ret = []
#     ret.append(DiskStackNodeLvmLv(util.rootLvDevPath, util.vgName, util.rootLvName))
#     if self._bSwapLv:
#         ret.append(DiskStackNodeLvmLv(util.swapLvDevPath, util.vgName, util.swapLvName))

#     for node in ret:
#         for d in self._diskList:
#             partNode = DiskStackNodePartition(util.devPathDiskToPartition(d, 2), DiskStackNodePartition.PART_TYPE_GPT, parent=node)
#             DiskStackNodeHarddisk(d, parent=partNode)

#     for d in self._diskList:
#         espNode = DiskStackNodePartition(util.devPathDiskToPartition(d, 1), DiskStackNodePartition.PART_TYPE_GPT)
#         DiskStackNodeHarddisk(d, parent=espNode)
#         ret.append(espNode)

#     return ret



# def get_disk_stack(self):
#     partNode = DiskStackNodePartition(self._hddRootParti, DiskStackNodePartition.PART_TYPE_MBR)
#     DiskStackNodeHarddisk(self._hdd, parent=partNode)

#     espNode = DiskStackNodePartition(self._hddEspParti, DiskStackNodePartition.PART_TYPE_GPT)
#     DiskStackNodeHarddisk(self._hdd, parent=espNode)

#     return [partNode, espNode]

