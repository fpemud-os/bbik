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
import shutil
import tarfile
import pathlib
import anytree
import robust_layer.simple_fops
from ordered_set import OrderedSet
from .bbki import InitramfsInstallError
from .util import Util
from .util import TempChdir
from .host_info import HostMountPoint
from .host_info import HostDiskLvmLv
from .host_info import HostDiskBcache
from .host_info import HostDiskNvmeDisk
from .host_info import HostDiskScsiDisk
from .host_info import HostDiskXenDisk
from .host_info import HostDiskVirtioDisk
from .host_info import HostDiskPartition
from .host_info import HostInfoUtil
from .kernel import BootEntryWrapper


class InitramfsInstaller:

    def __init__(self, bbki, boot_entry):
        self._bbki = bbki
        self._be = boot_entry
        self._beWrapper = BootEntryWrapper(self._be)
        self._initramfsTmpDir = os.path.join(self._bbki.config.tmp_dir, "initramfs")

        # trick: initramfs debug is seldomly needed
        self.trickDebug = False

    def install(self):
        self._checkDotCfgFile()
        if HostInfoUtil.getMountPoint(self._bbki._hostInfo, HostMountPoint.NAME_ROOT) is None:
            raise InitramfsInstallError("mount information for root filesystem is not specified")

        # prepare tmpdir
        robust_layer.simple_fops.rm(self._initramfsTmpDir)
        os.makedirs(self._initramfsTmpDir)

        # deduplicated disk list
        diskList = OrderedSet()
        for mp in self._bbki._hostInfo.mount_point_list:
            for rootDisk in mp.underlay_disk_list:
                for disk in anytree.PostOrderIter(rootDisk):
                    diskList.add(disk)

        # get kernel module file list (order is important)
        kmodList = OrderedSet()
        if True:
            kaliasList = OrderedSet()

            for disk in diskList:
                if isinstance(disk, HostDiskLvmLv):
                    kaliasList.add("dm_mod")
                elif isinstance(disk, HostDiskScsiDisk):
                    kaliasList.add(disk.host_controller_name)
                    kaliasList.add("sd_mod")
                elif isinstance(disk, HostDiskNvmeDisk):
                    kaliasList.add("nvme")
                elif isinstance(disk, HostDiskXenDisk):
                    kaliasList.add("xen-blkfront")
                elif isinstance(disk, HostDiskVirtioDisk):
                    kaliasList.add("virtio_pci")
                    kaliasList.add("virtio_blk")
                elif isinstance(disk, HostDiskBcache):
                    kaliasList.add("bcache")
                elif isinstance(disk, HostDiskPartition):
                    pass        # get kernel module for partition format
                else:
                    assert False

            for mp in self._bbki._hostInfo.mount_point_list:
                if mp.fs_type == HostMountPoint.FS_TYPE_VFAT:
                    buf = pathlib.Path(self._be.boot_entry.kernel_config_filepath).read_text()
                    kaliasList.add("vfat")
                    m = re.search("^CONFIG_FAT_DEFAULT_CODEPAGE=(\\S+)$", buf, re.M)
                    if m is not None:
                        kaliasList.add("nls_cp%s" % (m.group(1)))
                    else:
                        raise InitramfsInstallError("CONFIG_FAT_DEFAULT_CODEPAGE is missing in \"%s\"" % (self._be.boot_entry.kernel_config_filepath))
                    m = re.search("^CONFIG_FAT_DEFAULT_IOCHARSET=\\\"(\\S+)\\\"$", buf, re.M)
                    if m is not None:
                        kaliasList.add("nls_%s" % (m.group(1)))
                    else:
                        raise InitramfsInstallError("CONFIG_FAT_DEFAULT_IOCHARSET is missing in \"%s\"" % (self._be.boot_entry.kernel_config_filepath))
                elif mp.fs_type in [HostMountPoint.FS_TYPE_EXT4, HostMountPoint.FS_TYPE_BTRFS]:
                    kaliasList.add(mp.fs_type)
                else:
                    assert False

            for kalias in kaliasList:
                kmodList |= OrderedSet(self._be.get_kmod_filepaths(kalias, with_deps=True))

        # get firmware file list
        firmwareList = OrderedSet()
        for kmod in kmodList:
            firmwareList |= OrderedSet(self._be.get_firmware_filepaths(kmod))

        # get block device preparation operation list
        blkOpList = OrderedSet()
        if True:
            for disk in diskList:
                if isinstance(disk, HostDiskLvmLv):
                    blkOpList.add("lvm-lv-activate %s %s %s" % (disk.uuid, disk.vg_name, disk.lv_name))
                elif isinstance(disk, HostDiskBcache):
                    for cacheDev in disk.cache_dev_list:
                        blkOpList.add("bcache-cache-device-activate %s" % (cacheDev.uuid))
                    blkOpList.add("bcache-backing-device-activate %s %s" % (disk.uuid, disk.backing_dev.uuid))
                elif isinstance(disk, HostDiskScsiDisk):
                    # blkOpList.append("blkdev-wait sd* %s" % (Util.getBlkDevUuid(d.devPath))
                    pass
                elif isinstance(disk, HostDiskNvmeDisk):
                    pass
                elif isinstance(disk, HostDiskXenDisk):
                    pass
                elif isinstance(disk, HostDiskVirtioDisk):
                    pass
                elif isinstance(disk, HostDiskPartition):
                    # blkOpList.append("blkdev-wait sd* %s" % (Util.getBlkDevUuid(d.devPath))
                    pass
                else:
                    assert False

        # create basic structure for initramfs directory
        self._installDir("/bin", self._initramfsTmpDir)
        self._installDir("/dev", self._initramfsTmpDir)
        self._installDir("/etc", self._initramfsTmpDir)
        self._installDir("/lib", self._initramfsTmpDir)
        self._installDir("/lib64", self._initramfsTmpDir)
        self._installDir("/proc", self._initramfsTmpDir)
        self._installDir("/run", self._initramfsTmpDir)
        self._installDir("/sbin", self._initramfsTmpDir)
        self._installDir("/sys", self._initramfsTmpDir)
        self._installDir("/tmp", self._initramfsTmpDir)
        self._installDir("/usr/bin", self._initramfsTmpDir)
        self._installDir("/usr/sbin", self._initramfsTmpDir)
        self._installDir("/usr/lib", self._initramfsTmpDir)
        self._installDir("/usr/lib64", self._initramfsTmpDir)
        self._installDir("/var", self._initramfsTmpDir)
        self._installDir(self._beWrapper.modules_dir, self._initramfsTmpDir)
        self._installDir(self._beWrapper.firmware_dir, self._initramfsTmpDir)
        os.makedirs(os.path.join(self._initramfsTmpDir, "sysroot"))
        self._generatePasswd(os.path.join(self._initramfsTmpDir, "etc", "passwd"))
        self._generateGroup(os.path.join(self._initramfsTmpDir, "etc", "group"))

        # install kmod files
        for f in kmodList:
            self._copyToInitrd(f, self._initramfsTmpDir)

        # install firmware files
        for f in firmwareList:
            self._copyToInitrd(f, self._initramfsTmpDir)

        # install insmod binary
        if len(kmodList) > 0:
            self._installBin("/sbin/insmod", self._initramfsTmpDir)

        # install files for block device preparation
        self._installFilesBlkid(self._initramfsTmpDir)
        for disk in diskList:
            if isinstance(disk, HostDiskLvmLv):
                self._installFilesLvm(self._initramfsTmpDir)
            elif isinstance(disk, HostDiskBcache):
                pass
            elif isinstance(disk, HostDiskScsiDisk):
                pass
            elif isinstance(disk, HostDiskNvmeDisk):
                pass
            elif isinstance(disk, HostDiskXenDisk):
                pass
            elif isinstance(disk, HostDiskVirtioDisk):
                pass
            elif isinstance(disk, HostDiskPartition):
                pass
            else:
                assert False

        # install init executable to initramfs
        self._installInit(self._initramfsTmpDir)
        self._installStartupRc(self._initramfsTmpDir, kmodList, blkOpList, self.mntInfoDict)

        # install kernel modules, firmwares and executables for debugging, use bash as init
        if self.trickDebug:
            dstdir = os.path.join(self._initramfsTmpDir, self._beWrapper.modules_dir[1:])
            if os.path.exists(dstdir):
                shutil.rmtree(dstdir)
            shutil.copytree(self._beWrapper.modules_dir, dstdir, symlinks=True)

            dstdir = os.path.join(self._initramfsTmpDir, self._beWrapper.firmware_dir[1:])
            if os.path.exists(dstdir):
                shutil.rmtree(dstdir)
            shutil.copytree(self._beWrapper.firmware_dir, dstdir, symlinks=True)

            self._installBin("/bin/bash", self._initramfsTmpDir)
            self._installBin("/bin/cat", self._initramfsTmpDir)
            self._installBin("/bin/cp", self._initramfsTmpDir)
            self._installBin("/bin/dd", self._initramfsTmpDir)
            self._installBin("/bin/echo", self._initramfsTmpDir)
            self._installBin("/bin/ls", self._initramfsTmpDir)
            self._installBin("/bin/ln", self._initramfsTmpDir)
            self._installBin("/bin/mount", self._initramfsTmpDir)
            self._installBin("/bin/ps", self._initramfsTmpDir)
            self._installBin("/bin/rm", self._initramfsTmpDir)
            self._installBin("/bin/touch", self._initramfsTmpDir)
            self._installBin("/usr/bin/basename", self._initramfsTmpDir)
            self._installBin("/usr/bin/dirname", self._initramfsTmpDir)
            self._installBin("/usr/bin/find", self._initramfsTmpDir)
            self._installBin("/usr/bin/sleep", self._initramfsTmpDir)
            self._installBin("/usr/bin/tree", self._initramfsTmpDir)
            self._installBin("/usr/bin/xargs", self._initramfsTmpDir)
            self._installBin("/usr/bin/hexdump", self._initramfsTmpDir)

            self._installBin("/sbin/blkid", self._initramfsTmpDir)
            self._installBin("/sbin/switch_root", self._initramfsTmpDir)

            self._installBin("/bin/lsmod", self._initramfsTmpDir)
            self._installBin("/bin/modinfo", self._initramfsTmpDir)
            self._installBin("/sbin/modprobe", self._initramfsTmpDir)
            shutil.copytree("/etc/modprobe.d", os.path.join(self._initramfsTmpDir, "etc", "modprobe.d"), symlinks=True)

            self._installBin("/sbin/dmsetup", self._initramfsTmpDir)
            self._installBin("/sbin/lvm", self._initramfsTmpDir)

            if os.path.exists("/usr/bin/nano"):
                self._installBin("/usr/bin/nano", self._initramfsTmpDir)

            os.rename(os.path.join(self._initramfsTmpDir, "init"), os.path.join(self._initramfsTmpDir, "init.bak"))
            os.symlink("/bin/bash", os.path.join(self._initramfsTmpDir, "init"))

            with open(os.path.join(self._initramfsTmpDir, ".bashrc"), "w") as f:
                f.write("echo \"<initramfs-debug> Mounting basic file systems\"\n")
                f.write("mount -t sysfs none /sys\n")
                f.write("mount -t proc none /proc\n")
                f.write("mount -t devtmpfs none /dev\n")
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the usb drivers\"\n")
                dstdir = os.path.join(self._beWrapper.modules_dir, "kernel", "drivers", "usb")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the hid drivers\"\n")
                dstdir = os.path.join(self._beWrapper.modules_dir, "kernel", "drivers", "hid")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the input drivers\"\n")
                dstdir = os.path.join(self._beWrapper.modules_dir, "kernel", "drivers", "input")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

        # build the initramfs file and tar file
        with TempChdir(self._initramfsTmpDir):
            # initramfs file
            cmdStr = "/usr/bin/find . -print0 "
            cmdStr += "| /bin/cpio --null -H newc -o "
            cmdStr += "| /usr/bin/xz --format=lzma "            # it seems linux kernel config RD_XZ has bug, so we must use format lzma
            cmdStr += "> \"%s\" " % (self._be.boot_entry.initrd_file)
            Util.shellCall(cmdStr)

            # tar file
            with tarfile.open(self._be.boot_entry.initrd_tar_file, "w:bz2") as f:
                for fn in glob.glob("*"):
                    f.add(fn)

    def _generatePasswd(self, filename):
        with open(filename, "w") as f:
            f.write("root:x:0:0::/root:/bin/sh\n")
            f.write("nobody:x:65534:65534::/:/sbin/nologin\n")

    def _generateGroup(self, filename):
        with open(filename, "w") as f:
            f.write("tty:x:5:\n")
            f.write("kmem:x:9:\n")
            f.write("disk:x:6:adm\n")
            f.write("floppy:x:11:\n")
            f.write("cdrom:x:19:\n")

    def _installDir(self, dirFilename, rootDir):
        assert dirFilename.startswith("/")

        if not os.path.isdir(dirFilename):
            raise Exception("\"%s\" is not a directory" % (dirFilename))

        dstDir = rootDir + dirFilename
        if os.path.islink(dirFilename):
            dirname = os.path.dirname(dstDir)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            os.symlink(os.readlink(dirFilename), dstDir)
        else:
            os.makedirs(dstDir)

    def _installBin(self, binFilename, rootDir):
        self._copyToInitrd(binFilename, rootDir)
        for df in Util.libUsed(binFilename):
            self._copyToInitrd(df, rootDir)

    def _installBinFromInitDataDir(self, binFilename, rootDir, targetDir):
        srcFilename = os.path.join(FmConst.libInitrdDir, binFilename)
        dstFilename = os.path.join(rootDir, targetDir, binFilename)

        Util.cmdCall("/bin/cp", "-f", srcFilename, dstFilename)
        Util.cmdCall("/bin/chmod", "755", dstFilename)

        for df in Util.libUsed(dstFilename):
            self._copyToInitrd(df, rootDir)

    def _installFilesLvm(self, rootDir):
        self._installBinFromInitDataDir("lvm-lv-activate", rootDir, "usr/sbin")

        # note: surrounded " would be recognized as part of rootDir, it's a bug of systemd-tmpfiles
        Util.cmdCall("/bin/systemd-tmpfiles", "--create", "--root=%s" % (rootDir), "/usr/lib/tmpfiles.d/lvm2.conf")

        etcDir = os.path.join(rootDir, "etc", "lvm")
        if not os.path.exists(etcDir):
            os.mkdir(etcDir)
        with open(os.path.join(etcDir, "lvm.conf"), "w") as f:
            f.write("global {\n")
            f.write("    locking_type = 4\n")
            f.write("    use_lvmetad = 0\n")
            f.write("}\n")
            f.write("devices {\n")
            f.write("    write_cache_state = 0\n")
            f.write("}\n")
            f.write("backup {\n")
            f.write("    backup = 0\n")
            f.write("    archive = 0\n")
            f.write("}\n")

    def _installFilesBlkid(self, rootDir):
        etcDir = os.path.join(rootDir, "etc")
        if not os.path.exists(etcDir):
            os.mkdir(etcDir)
        with open(os.path.join(etcDir, "blkid.conf"), "w") as f:
            f.write("EVALUATE=scan\n")

    def _installInit(self, rootDir):
        self._installBinFromInitDataDir("init", rootDir, "")

    def _installStartupRc(self, rootDir, kmodList, blkOpList):
        buf = ""
        initCmdline = self._bbki.config.get_system_init_info()[1]

        def _getPrefixedMountPoint(mi):
            return os.path.join("/sysroot", mi.mount_point[1:])

        # write comments
        for mi in self._bbki._targetHostInfo.mount_point_list:
            buf += "# uuid(%s)=%s\n" % (mi.name, mi.dev_uuid)
        buf += "\n"

        # load kernel modules
        if len(kmodList) > 0:
            for k in kmodList:
                buf += "insmod \"%s\"\n" % (k)
            buf += "\n"

        # prepare block devices
        if len(blkOpList) > 0:
            for k in blkOpList:
                buf += "%s\n" % (k)
            buf += "\n"

        # mount block devices
        for mi in self._bbki._targetHostInfo.mount_point_list:
            buf += "mount -t %s -o \"%s\" \"UUID=%s\" \"%s\"\n" % (mi.fs_type, mi.mnt_opt, mi.dev_uuid, _getPrefixedMountPoint(mi))
            buf += "\n"

        # switch to new root
        buf += ("switchroot \"/sysroot\" %s\n" % (initCmdline)).rstrip()
        buf += "\n"

        # write cfg file
        with open(os.path.join(rootDir, "startup.rc"), "w") as f:
            f.write(buf)

    def _copyToInitrd(self, filename, rootDir):
        assert os.path.isabs(filename)
        while True:
            if os.path.islink(filename):
                self._copyToInitrdImplLink(filename, rootDir)
                filename = os.path.join(os.path.dirname(filename), os.readlink(filename))
            else:
                self._copyToInitrdImplFile(filename, rootDir)
                break

    def _copyToInitrdImplLink(self, filename, rootDir):
        dstfile = os.path.join(rootDir, filename[1:])
        if os.path.exists(dstfile):
            return
        dstdir = os.path.dirname(dstfile)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)
        linkto = os.readlink(filename)
        os.symlink(linkto, dstfile)

    def _copyToInitrdImplFile(self, filename, rootDir):
        dstfile = os.path.join(rootDir, filename[1:])
        if os.path.exists(dstfile):
            return
        dstdir = os.path.dirname(dstfile)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)
        Util.cmdCall("/bin/cp", "-f", filename, dstfile)

    def _checkDotCfgFile(self):
        symDict = {
            "RD_XZ": "y",
            "RD_LZMA": "y",         # it seems RD_XZ has no effect, we have to enable RD_LZMA, kernel bug?
            "BCACHE": "m",
            "BLK_DEV_SD": "m",
            "BLK_DEV_DM": "m",
            "EXT4_FS": "m",
            "VFAT_FS": "m",
        }

        buf = pathlib.Path(self._be.boot_entry.kernel_config_file).read_text()
        for k, v in symDict.items():
            if not re.fullmatch("%s=%s" % (k, v), buf, re.M):
                raise InitramfsInstallError("config symbol %s must be selected as \"%s\"!" % (k, v))
