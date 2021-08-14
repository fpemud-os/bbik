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


class InitramfsInstaller:

    def __init__(self, bbki, kernel_instance):
        self._bbki = bbki
        self._kernel = kernel_instance
        self._kernelModuleDir = self._bbki._fsLayout.get_kernel_modules_dir(self._kernel.verstr)
        self._initramfsTmpDir = os.path.join(self._bbki.config.tmp_dir, "initramfs")

        # trick: initramfs debug is seldomly needed
        self.trickDebug = False

    def install(self):
        if HostInfoUtil.getMountPointByType(self._bbki._hostInfo, HostMountPoint.MOUNT_TYPE_ROOT) is None:
            raise InitramfsInstallError("mount information for root filesystem is not specified")

        # prepare tmpdir
        robust_layer.simple_fops.rm(self._initramfsTmpDir)
        os.makedirs(self._initramfsTmpDir)

        # variables
        rootDir = self._initramfsTmpDir
        etcDir = os.path.join(rootDir, "etc")

        # create basic structure for initramfs directory
        self._installDir("/bin", rootDir)
        self._installDir("/dev", rootDir)
        self._installDir("/etc", rootDir)
        self._installDir("/lib", rootDir)
        self._installDir("/lib64", rootDir)
        self._installDir("/proc", rootDir)
        self._installDir("/run", rootDir)
        self._installDir("/sbin", rootDir)
        self._installDir("/sys", rootDir)
        self._installDir("/tmp", rootDir)
        self._installDir("/usr/bin", rootDir)
        self._installDir("/usr/sbin", rootDir)
        self._installDir("/usr/lib", rootDir)
        self._installDir("/usr/lib64", rootDir)
        self._installDir("/var", rootDir)
        self._installDir(self._kernelModuleDir, rootDir)
        self._installDir(self._bbki._fsLayout.firmware_dir, rootDir)
        os.makedirs(os.path.join(rootDir, "sysroot"))
        self._generatePasswd(os.path.join(etcDir, "passwd"))
        self._generateGroup(os.path.join(etcDir, "group"))

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
                    buf = pathlib.Path(self._kernel.boot_entry.kernel_config_filepath).read_text()
                    kaliasList.add("vfat")
                    m = re.search("^CONFIG_FAT_DEFAULT_CODEPAGE=(\\S+)$", buf, re.M)
                    if m is not None:
                        kaliasList.add("nls_cp%s" % (m.group(1)))
                    else:
                        raise InitramfsInstallError("CONFIG_FAT_DEFAULT_CODEPAGE is missing in \"%s\"" % (self._kernel.boot_entry.kernel_config_filepath))
                    m = re.search("^CONFIG_FAT_DEFAULT_IOCHARSET=\\\"(\\S+)\\\"$", buf, re.M)
                    if m is not None:
                        kaliasList.add("nls_%s" % (m.group(1)))
                    else:
                        raise InitramfsInstallError("CONFIG_FAT_DEFAULT_IOCHARSET is missing in \"%s\"" % (self._kernel.boot_entry.kernel_config_filepath))
                elif mp.fs_type in [HostMountPoint.FS_TYPE_EXT4, HostMountPoint.FS_TYPE_BTRFS]:
                    kaliasList.add(mp.fs_type)
                else:
                    assert False

            for kalias in kaliasList:
                kmodList |= OrderedSet(self._kernel.get_kmod_filepaths(kalias, with_deps=True))

        # get firmware file list
        firmwareList = OrderedSet()
        for kmod in kmodList:
            firmwareList |= OrderedSet(self._kernel.get_firmware_filepaths(kmod))

        # install kmod files
        for f in kmodList:
            self._copyToInitrd(f, rootDir)

        # install firmware files
        for f in firmwareList:
            self._copyToInitrd(f, rootDir)

        # install insmod binary
        if len(kmodList) > 0:
            self._installBin("/sbin/insmod", rootDir)

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

        # install files for block device preparation
        self._installFilesBlkid(rootDir)
        for disk in diskList:
            if isinstance(disk, HostDiskLvmLv):
                self._installFilesLvm(rootDir)
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
        self._installInit(rootDir)
        self._installStartupRc(rootDir, kmodList, blkOpList, self.mntInfoDict, FmConst.kernelInitCmd)

        # install kernel modules, firmwares and executables for debugging, use bash as init
        if self.trickDebug:
            dstdir = os.path.join(rootDir, self._kernelModuleDir[1:])
            if os.path.exists(dstdir):
                shutil.rmtree(dstdir)
            shutil.copytree(self._kernelModuleDir, dstdir, symlinks=True)

            dstdir = os.path.join(rootDir, self._bbki._fsLayout.firmware_dir[1:])
            if os.path.exists(dstdir):
                shutil.rmtree(dstdir)
            shutil.copytree(self._bbki._fsLayout.firmware_dir, dstdir, symlinks=True)

            self._installBin("/bin/bash", rootDir)
            self._installBin("/bin/cat", rootDir)
            self._installBin("/bin/cp", rootDir)
            self._installBin("/bin/dd", rootDir)
            self._installBin("/bin/echo", rootDir)
            self._installBin("/bin/ls", rootDir)
            self._installBin("/bin/ln", rootDir)
            self._installBin("/bin/mount", rootDir)
            self._installBin("/bin/ps", rootDir)
            self._installBin("/bin/rm", rootDir)
            self._installBin("/bin/touch", rootDir)
            self._installBin("/usr/bin/basename", rootDir)
            self._installBin("/usr/bin/dirname", rootDir)
            self._installBin("/usr/bin/find", rootDir)
            self._installBin("/usr/bin/sleep", rootDir)
            self._installBin("/usr/bin/tree", rootDir)
            self._installBin("/usr/bin/xargs", rootDir)
            self._installBin("/usr/bin/hexdump", rootDir)

            self._installBin("/sbin/blkid", rootDir)
            self._installBin("/sbin/switch_root", rootDir)

            self._installBin("/bin/lsmod", rootDir)
            self._installBin("/bin/modinfo", rootDir)
            self._installBin("/sbin/modprobe", rootDir)
            shutil.copytree("/etc/modprobe.d", os.path.join(rootDir, "etc", "modprobe.d"), symlinks=True)

            self._installBin("/sbin/dmsetup", rootDir)
            self._installBin("/sbin/lvm", rootDir)

            if os.path.exists("/usr/bin/nano"):
                self._installBin("/usr/bin/nano", rootDir)

            os.rename(os.path.join(rootDir, "init"), os.path.join(rootDir, "init.bak"))
            os.symlink("/bin/bash", os.path.join(rootDir, "init"))

            with open(os.path.join(rootDir, ".bashrc"), "w") as f:
                f.write("echo \"<initramfs-debug> Mounting basic file systems\"\n")
                f.write("mount -t sysfs none /sys\n")
                f.write("mount -t proc none /proc\n")
                f.write("mount -t devtmpfs none /dev\n")
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the usb drivers\"\n")
                dstdir = os.path.join(self._kernelModuleDir, "kernel", "drivers", "usb")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the hid drivers\"\n")
                dstdir = os.path.join(self._kernelModuleDir, "kernel", "drivers", "hid")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the input drivers\"\n")
                dstdir = os.path.join(self._kernelModuleDir, "kernel", "drivers", "input")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

        # build the initramfs file and tar file
        with TempChdir(rootDir):
            # initramfs file
            cmdStr = "/usr/bin/find . -print0 "
            cmdStr += "| /bin/cpio --null -H newc -o "
            cmdStr += "| /usr/bin/xz --format=lzma "            # it seems linux kernel config RD_XZ has bug, so we must use format lzma
            cmdStr += "> \"%s\" " % (self._kernel.boot_entry.initrd_file)
            Util.shellCall(cmdStr)

            # tar file
            with tarfile.open(self._kernel.boot_entry.initrd_tar_file, "w:bz2") as f:
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

    def _installStartupRc(self, rootDir, kmodList, blkOpList, mntInfoDict):
        buf = ""

        # write comments
        for name, obj in mntInfoDict.items():
            if obj is not None:
                buf += "# uuid(%s)=%s\n" % (name, Util.getBlkDevUuid(mntInfoDict[name].devPath))
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

        # mount root
        if True:
            mi = mntInfoDict["root"]
            uuid = Util.getBlkDevUuid(mi.devPath)
            buf += "mount -t %s -o \"%s\" \"UUID=%s\" \"%s\"\n" % (mi.fsType, mi.mntOpt, uuid, "/sysroot")
            buf += "\n"

        # mount boot
        if mntInfoDict["boot"] is not None:
            mi = mntInfoDict["boot"]
            uuid = Util.getBlkDevUuid(mi.devPath)
            buf += "mount -t %s -o \"%s\" \"UUID=%s\" \"%s\"\n" % (mi.fsType, mi.mntOpt, uuid, os.path.join("/sysroot", "boot"))
            buf += "\n"

        # switch to new root
        initName, initCmdline = self._bbki.config.get_system_init_info()
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

        buf = pathlib.Path(self._kernel.boot_entry.kernel_config_file).read_text()
        for k, v in symDict.items():
            if not re.fullmatch("%s=%s" % (k, v), buf, re.M):
                raise InitramfsInstallError("config symbol %s must be selected as \"%s\"!" % (k, v))
