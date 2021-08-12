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
                assert len([x for x in mount_point_list if x.mount_type == HostMountPointInfo.MOUNT_TYPE_ROOT]) == 1
                ret = [x for x in mount_point_list if x.mount_type == HostMountPointInfo.MOUNT_TYPE_BOOT]
                assert len(ret) == 1
                assert self.boot_disk == Util.devPathPartitionToDisk(ret[0])
            elif boot_mode == Bbki.BOOT_MODE_BIOS:
                assert len([x for x in mount_point_list if x.mount_type == HostMountPointInfo.MOUNT_TYPE_ROOT]) == 1
                assert len([x for x in mount_point_list if x.mount_type == HostMountPointInfo.MOUNT_TYPE_BOOT]) == 0
                assert self.boot_disk is not None
            else:
                assert False
            self.mount_point_list = mount_point_list
        else:
            assert self.boot_disk is None


class HostMountPointInfo:

    def __init__(self, mount_type, mount_point, dev_path, fs_type, mount_option=""):
        assert self.MOUNT_TYPE_ROOT <= mount_type <= self.MOUNT_TYPE_OTHER
        assert Util.isValidFsType(fs_type)

        self.mount_type = mount_type
        self.dev_path = dev_path
        self.mount_point = mount_point
        self.fs_type = fs_type
        self.mount_option = ""              # FIXME
