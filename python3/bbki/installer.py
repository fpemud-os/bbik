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
import kmod
import glob
import shutil
import tarfile
import pathlib
import anytree
import pylkcutil
import pkg_resources
import robust_layer.simple_fops
from ordered_set import OrderedSet
from .util import Util
from .util import TempChdir
from .po import HostMountPoint
from .po import HostDiskLvmLv
from .po import HostDiskBcache
from .po import HostDiskNvmeDisk
from .po import HostDiskScsiDisk
from .po import HostDiskXenDisk
from .po import HostDiskVirtioDisk
from .po import HostDiskPartition
from .po import HostInfoUtil
from .boot_entry import BootEntry, BootEntryUtils
from .repo import BbkiFileExecutor
from .exception import InitramfsInstallError


class BootEntryInstaller:

    def __init__(self, bbki, kernel_atom, kernel_atom_item_list):
        self._bbki = bbki

        self._kernelAtom = kernel_atom
        self._addonAtomList = kernel_atom_item_list

        self._executorDict = dict()
        self._executorDict[kernel_atom] = BbkiFileExecutor(kernel_atom)
        for item in kernel_atom_item_list:
            self._executorDict[item] = BbkiFileExecutor(item)

        # create tmpdirs
        self._executorDict[self._kernelAtom].create_tmpdirs()
        for item in self._addonAtomList:
            self._executorDict[item].create_tmpdirs()

    def dispose(self):
        for item in reversed(self._addonAtomList):
            self._executorDict[item].remove_tmpdirs()
        self._executorDict[self._kernelAtom].remove_tmpdirs()

    def get_target_boot_entry(self):
        return BootEntry.new_from_verstr(self._bbki, "native", self._kernelAtom.verstr)

    def unpack(self):
        self._executorDict[self._kernelAtom].src_unpack()
        for item in self._addonAtomList:
            self._executorDict[item].exec_src_unpack()

    def patch_kernel(self):
        for addon_item in self._addonAtomList:
            self._executorDict[addon_item].exec_kernel_addon_patch_kernel(self._kernelAtom)

    def generate_kernel_dotcfg(self):
        rulesDict = dict()
        workDir = self._executorDict[self._kernelAtom].get_workdir()
        kcfgRulesTmpFile = os.path.join(workDir, "config.rules")
        dotCfgFile = os.path.join(workDir, ".config")

        # head rules
        if True:
            buf = ""

            # default hostname
            buf += "DEFAULT_HOSTNAME=\"(none)\"\n"
            buf += "\n"

            # deprecated symbol, but many drivers still need it
            buf += "FW_LOADER=y\n"
            buf += "\n"

            # atk9k depends on it
            buf += "DEBUG_FS=y\n"
            buf += "\n"

            # H3C CAS 2.0 still use legacy virtio device, so it is needed
            buf += "VIRTIO_PCI_LEGACY=y\n"
            buf += "\n"

            # we still need iptables
            buf += "NETFILTER_XTABLES=y\n"
            buf += "IP_NF_IPTABLES=y\n"
            buf += "IP_NF_ARPTABLES=y\n"
            buf += "\n"

            # it seems we still need this, why?
            buf += "FB=y\n"
            buf += "DRM_FBDEV_EMULATION=y\n"
            buf += "\n"

            # net-wireless/iwd needs them, FIXME
            buf += "PKCS8_PRIVATE_KEY_PARSER=y\n"
            buf += "KEY_DH_OPERATIONS=y\n"
            buf += "\n"

            # debug feature
            if True:
                # killing CONFIG_VT is failed for now
                buf += "TTY=y\n"
                buf += "[symbols:VT]=y\n"
                buf += "[symbols:/Device Drivers/Graphics support/Console display driver support]=y\n"
                buf += "\n"

            # symbols we dislike
            buf += "[debugging-symbols:/]=n\n"
            buf += "[deprecated-symbols:/]=n\n"
            buf += "[workaround-symbols:/]=n\n"
            buf += "[experimental-symbols:/]=n\n"
            buf += "[dangerous-symbols:/]=n\n"
            buf += "\n"

            rulesDict["head"] = buf

        # build-in rules
        for fn in sorted(pkg_resources.resource_listdir(__name__, "kernel-config-rules")):
            if not fn.endswith(".rules"):
                continue
            m = re.fullmatch(r'([0-9]+-)?(.*)\.rules', fn)
            if m is not None:
                rname = m.group(2)
            rulesDict[rname] = pkg_resources.resource_string(__name__, os.path.join("kernel-config-rules", fn)).decode("iso8859-1")

        # addon rules
        for addon_item in self._addonAtomList:
            buf = self._executorDict[addon_item].exec_kernel_addon_contribute_config_rules()
            rulesDict[addon_item.name] = buf

        # sysadmin rules
        rulesDict["custom"] = ""            # FIXME

        # generate .config file
        with open(kcfgRulesTmpFile, "w") as f:
            for name, buf in rulesDict.items():
                f.write("## %s ######################\n" % (name))
                f.write("\n")
                f.write(buf)
                f.write("\n")
                f.write("\n")
                f.write("\n")

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            Util.shellCall("/bin/sed -i '/VT=n/d' %s" % (kcfgRulesTmpFile))

        # generate the real ".config"
        # FIXME: moved here from a seperate process, leakage?
        pylkcutil.generator.generate(workDir, "allnoconfig+module", kcfgRulesTmpFile, output=dotCfgFile)

        # "make olddefconfig" may change the .config file further
        with TempChdir(workDir):
            Util.shellCall("make olddefconfig")

    def build_kernel(self):
        self._executorDict[self._kernelAtom].exec_kernel_build()
        for item in self._addonAtomList:
            self._executorDict[item].exec_kernel_addon_build()

    def install_kernel(self):
        self._executorDict[self._kernelAtom].exec_kernel_install()
        for item in self._addonAtomList:
            self._executorDict[item].exec_kernel_addon_install()

    def install_initramfs(self):
        InitramfsInstaller(self._bbki, self.get_target_boot_entry()).install()

    def clean_historical_boot_entries(self):
        os.makedirs(self._bbki._fsLayout.get_boot_history_dir(), exist_ok=True)
        for be in BootEntryUtils.getBootEntryList():
            if be != self.get_target_boot_entry():
                for fullfn in BootEntryUtils.getBootEntryFilePathList:
                    shutil.move(fullfn, self._bbki._fsLayout.get_boot_history_dir())


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
        if self._targetHostInfo.mount_point_list is None:
            raise InitramfsInstallError("no boot/root device specified")
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
        for km in kmodList:
            firmwareList |= OrderedSet(self._be.get_firmware_filepaths(km))

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
        srcFilename = pkg_resources.resource_filename(__name__, binFilename)
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


class BootEntryWrapper:

    def __init__(self, boot_entry):
        self._bootEntry = boot_entry
        self._modulesDir = self._bbki._fsLayout.get_kernel_modules_dir(self._bootEntry.verstr)

    @property
    def modules_dir(self):
        return self._modulesDir

    @property
    def firmware_dir(self):
        return self._bbki._fsLayout.get_firmware_dir()

    @property
    def src_arch(self):
        # FIXME: what's the difference with arch?

        if self._bootEntry.arch == "i386" or self._bootEntry.arch == "x86_64":
            return "x86"
        elif self._bootEntry.arch == "sparc32" or self._bootEntry.arch == "sparc64":
            return "sparc"
        elif self._bootEntry.arch == "sh":
            return "sh64"
        else:
            return self._bootEntry.arch

    def get_kmod_filenames(self, kmod_alias, with_deps=False):
        return [x[len(self._modulesDir):] for x in self.get_kmod_filepaths(kmod_alias, with_deps)]

    def get_kmod_filepaths(self, kmod_alias, with_deps=False):
        kmodList = dict()                                           # use dict to remove duplication while keeping order
        ctx = kmod.Kmod(self._modulesDir.encode("utf-8"))           # FIXME: why encode is neccessary?
        self._getKmodAndDeps(ctx, kmod_alias, with_deps, kmodList)
        return list(kmodList.fromkeys())

    def get_firmware_filenames(self, kmod_filepath):
        return self._getFirmwareImpl(kmod_filepath, True)

    def get_firmware_filepaths(self, kmod_filepath):
        return self._getFirmwareImpl(kmod_filepath, False)

    def _getFirmwareImpl(self, kmodFilePath, bReturnNameOrPath):
        ret = []

        # python-kmod bug: can only recognize the last firmware in modinfo
        # so use the command output of modinfo directly
        for line in Util.cmdCall("/bin/modinfo", kmodFilePath).split("\n"):
            m = re.fullmatch("firmware: +(\\S.*)", line)
            if m is not None:
                if bReturnNameOrPath:
                    ret.append(m.group(1))
                else:
                    ret.append(os.path.join(self._bbki._fsLayout.get_firmware_dir(), m.group(1)))

        # add standard files
        standardFiles = [
            ".ctime",
            "regulatory.db",
            "regulatory.db.p7s",
        ]
        if bReturnNameOrPath:
            ret += standardFiles
        else:
            ret += [os.path.join(self._bbki._fsLayout.get_firmware_dir(), x) for x in standardFiles]

        # return value
        return ret

    def _getKmodAndDeps(self, ctx, kmodAlias, withDeps, result):
        kmodObjList = list(ctx.lookup(kmodAlias))
        if len(kmodObjList) > 0:
            assert len(kmodObjList) == 1
            kmodObj = kmodObjList[0]

            if withDeps and "depends" in kmodObj.info and kmodObj.info["depends"] != "":
                for kmodAlias in kmodObj.info["depends"].split(","):
                    self._getKmodAndDeps(ctx, kmodAlias, result)

            if kmodObj.path is not None:
                # this module is not built into the kernel
                result[kmodObj.path] = None
