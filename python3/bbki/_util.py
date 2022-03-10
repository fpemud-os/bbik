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
import time
import psutil
import pathlib
import subprocess


class Util:

    @staticmethod
    def findInList(lst, key):
        for x in lst:
            if key(x):
                return x
        assert False

    @staticmethod
    def checkListUnique(lst, key=None):
        if key is None:
            keyList = lst
        else:
            keyList = [key(x) for x in lst]
        return len(keyList) == len(set(keyList))

    @staticmethod
    def globDirRecursively(dirpath, excludeSelf=False):
        # glob.glob("/a/**", recursive=True) returns ["/a/", "/a/a", "/a/a/a", ...]
        # the first element sucks, normalize it
        ret = glob.glob(os.path.join(dirpath, "**"), recursive=True)
        assert ret[0] == dirpath + "/"
        if excludeSelf:
            ret.pop(0)
        else:
            ret[0] = dirpath
        return ret

    @staticmethod
    def getBlkDevUuid(devPath):
        """UUID is also called FS-UUID, only device containing a file system has it, note that all btrfs device has same UUID"""

        ret = Util.cmdCall("/sbin/blkid", devPath)
        m = re.search(r'\bUUID="(\S*)"\B', ret, re.M)
        if m is not None:
            return m.group(1)
        return None

    @staticmethod
    def getBlkDevByUuid(uuid):
        path = os.path.join("/dev", "disk", "by-uuid", uuid)
        if not os.path.exists(path):
            return None
        return os.path.realpath(path)

    @staticmethod
    def getBlkDevSubUuid(devPath):
        """UUID_SUB is special UUID for btrfs device"""

        ret = Util.cmdCall("/sbin/blkid", devPath)
        m = re.search(r'\bUUID_SUB="(\S*)"\B', ret, re.M)
        if m is not None:
            return m.group(1)
        return None

    @staticmethod
    def getBlkDevBySubUuid(uuid):
        devName = None
        for line in Util.cmdCall("blkid", "-o", "export").split("\n"):
            m = re.fullmatch("DEVNAME=(\\S+)", line)
            if m is not None:
                devName = m.group(1)
                continue
            m = re.fullmatch("UUID_SUB=(\\S+)", line)
            if m is not None and m.group(1) == uuid:
                break
        return devName

    @staticmethod
    def getBlkDevPartUuid(devPath):
        """only disk partition has PARTUUID"""

        ret = Util.cmdCall("/sbin/blkid", devPath)
        m = re.search(r'\bPARTUUID="(\S*)"\B', ret, re.M)
        if m is not None:
            return m.group(1)
        return None

    @staticmethod
    def getBlkDevByPartUuid(uuid):
        path = os.path.join("/dev", "disk", "by-partuuid", uuid)
        if not os.path.exists(path):
            return None
        return os.path.realpath(path)

    @staticmethod
    def splitToTuple(s, d, count):
        ret = s.split(d)
        assert len(ret) == count
        return tuple(ret)

    @staticmethod
    def isValidKernelArch(archStr):
        return True

    @staticmethod
    def isValidKernelVer(verStr):
        return True

    @staticmethod
    def readListFile(filename):
        ret = []
        with open(filename, "r") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if line != "" and not line.startswith("#"):
                    ret.append(line)
        return ret

    @staticmethod
    def addItemToListFile(item, filename):
        with open(filename, "a") as f:
            f.write("\n")
            f.write(item)
            f.write("\n")

    @staticmethod
    def compareVerstr(verstr1, verstr2):
        """eg: 3.9.11-gentoo-r1 or 3.10.7-gentoo"""

        partList1 = verstr1.split("-")
        partList2 = verstr2.split("-")

        verList1 = partList1[0].split(".")
        verList2 = partList2[0].split(".")
        assert len(verList1) == 3 and len(verList2) == 3

        ver1 = int(verList1[0]) * 10000 + int(verList1[1]) * 100 + int(verList1[2])
        ver2 = int(verList2[0]) * 10000 + int(verList2[1]) * 100 + int(verList2[2])
        if ver1 > ver2:
            return 1
        elif ver1 < ver2:
            return -1

        if len(partList1) >= 2 and len(partList2) == 1:
            return 1
        elif len(partList1) == 1 and len(partList2) >= 2:
            return -1

        p1 = "-".join(partList1[1:])
        p2 = "-".join(partList2[1:])
        if p1 > p2:
            return 1
        elif p1 < p2:
            return -1

        return 0

    @staticmethod
    def cmdCall(cmd, *kargs):
        # call command to execute backstage job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminated by signal, not by detecting child-process failure
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller is terminated by signal, and NOT notify callee
        #   * callee must auto-terminate, and cause no side-effect, after caller is terminated
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment

        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def cmdCallTestSuccess(cmd, *kargs):
        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        return (ret.returncode == 0)

    @staticmethod
    def shellCall(cmd):
        # call command with shell to execute backstage job
        # scenarios are the same as Util.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def shellCallWithRetCode(cmd):
        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        return (ret.returncode, ret.stdout.rstrip())

    @staticmethod
    def bcachefsGetUuid(slaveDevPathList):
        ret = None
        for devPath in slaveDevPathList:
            out = Util.cmdCall("file", "-sb", devPath)
            m = re.search("^bcachefs, UUID=(\\S+),", out)
            if ret is None:
                ret = m.group(1)
            else:
                assert ret == m.group(1)
        return ret

    @staticmethod
    def btrfsGetUuid(mountPoint):
        out = Util.cmdCall("btrfs", "filesystem", "show", mountPoint)
        m = re.search("uuid: (\\S+)", out, re.M)
        return m.group(1)

    @staticmethod
    def btrfsGetSlavePathList(mountPoint):
        ret = []
        out = Util.cmdCall("btrfs", "filesystem", "show", mountPoint)
        for m in re.finditer("path (\\S+)", out, re.M):
            ret.append(m.group(1))
        return ret

    @staticmethod
    def bcacheGetSlaveDevPathList(bcacheDevPath):
        """Last element in the returned list is the backing device, others are cache device"""

        retList = []

        slavePath = "/sys/block/" + os.path.basename(bcacheDevPath) + "/slaves"
        for slaveDev in os.listdir(slavePath):
            retList.append(os.path.join("/dev", slaveDev))

        bcachePath = os.path.realpath("/sys/block/" + os.path.basename(bcacheDevPath) + "/bcache")
        backingDev = os.path.basename(os.path.dirname(bcachePath))
        backingDevPath = os.path.join("/dev", backingDev)

        retList.remove(backingDevPath)
        retList.append(backingDevPath)
        return retList

    @staticmethod
    def scsiGetHostControllerName(devPath):
        devName = os.path.basename(os.path.realpath(devPath))       # XXX -> /dev/sda => sda
        sysfsPath = os.path.join("/sys", "block", devName)          # sda => /sys/block/sda
        hostPath = os.path.realpath(sysfsPath)                      # /sys/block/sda -> /sys/block/devices/pci0000:00/0000:00:17.0/ata3/host2/target2:0:0/2:0:0:0/block/sda
        while True:
            m = re.search("^host[0-9]+$", os.path.basename(hostPath), re.M)
            if m is not None:
                hostControllerNameFile = os.path.join("/sys", "class", "scsi_host", m.group(0), "proc_name")
                return pathlib.Path(hostControllerNameFile).read_text().rstrip()
            hostPath = os.path.dirname(hostPath)
            assert hostPath != "/"

    @staticmethod
    def getBlkDevLvmInfo(devPath):
        """Returns (vg-name, lv-name)
           Returns None if the device is not lvm"""

        rc, out = Util.shellCallWithRetCode("dmsetup info %s" % (devPath))
        if rc == 0:
            m = re.search("^Name: *(\\S+)$", out, re.M)
            assert m is not None
            ret = m.group(1).split(".")
            if len(ret) == 2:
                return ret
            ret = m.group(1).split("-")         # compatible with old lvm version
            if len(ret) == 2:
                return ret

        m = re.fullmatch("(/dev/mapper/\\S+)-(\\S+)", devPath)          # compatible with old lvm version
        if m is not None:
            return Util.getBlkDevLvmInfo("%s-%s" % (m.group(1), m.group(2)))

        return None

    @staticmethod
    def lvmGetSlaveDevPathList(vgName):
        ret = []
        out = Util.cmdCall("/sbin/lvm", "pvdisplay", "-c")
        for m in re.finditer("^\\s*(\\S+):%s:.*" % (vgName), out, re.M):
            if m.group(1) == "[unknown]":
                raise Exception("volume group %s not fully loaded" % (vgName))
            ret.append(m.group(1))
        return ret

    @staticmethod
    def getBlkDevFsType(devPath):
        # FIXME: blkid doesn't support bcachefs yet, use file instead
        ret = Util.cmdCall("file", "-sb", devPath)
        if re.search("^bcachefs, UUID=", ret) is not None:
            return "bcachefs"

        # use blkid to get fstype
        ret = Util.cmdCall("blkid", "-o", "export", devPath)
        m = re.search("^TYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1).lower()

        return ""

    @staticmethod
    def libUsed(binFile):
        """Return a list of the paths of the shared libraries used by binFile"""

        LDD_STYLE1 = re.compile(r'^\t(.+?)\s\=\>\s(.+?)?\s\(0x.+?\)$')
        LDD_STYLE2 = re.compile(r'^\t(.+?)\s\(0x.+?\)$')

        try:
            raw_output = Util.cmdCall("/usr/bin/ldd", "--", binFile)
        except subprocess.CalledProcessError as e:
            if 'not a dynamic executable' in e.output:
                raise Exception("not a dynamic executable")
            else:
                raise

        # We can expect output like this:
        # [tab]path1[space][paren]0xaddr[paren]
        # or
        # [tab]path1[space+]=>[space+]path2?[paren]0xaddr[paren]
        # path1 can be ignored if => appears
        # path2 could be empty

        if 'statically linked' in raw_output:
            return []

        result = []
        for line in raw_output.splitlines():
            match = LDD_STYLE1.match(line)
            if match is not None:
                if match.group(2):
                    result.append(match.group(2))
                continue

            match = LDD_STYLE2.match(line)
            if match is not None:
                result.append(match.group(1))
                continue

            assert False

        result.remove("linux-vdso.so.1")
        return result

    @staticmethod
    def devPathPartitionToDiskAndPartitionId(partitionDevPath):
        m = re.fullmatch("(/dev/sd[a-z])([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        m = re.fullmatch("(/dev/xvd[a-z])([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        m = re.fullmatch("(/dev/vd[a-z])([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        m = re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)p([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        assert False

    @staticmethod
    def devPathPartitionToDisk(partitionDevPath):
        return Util.devPathPartitionToDiskAndPartitionId(partitionDevPath)[0]

    @staticmethod
    def devPathPartitionOrDiskToDisk(devPath):
        if re.fullmatch(".*[0-9]+", devPath):
            return Util.devPathPartitionToDiskAndPartitionId(devPath)[0]
        else:
            return devPath


class TempChdir:

    def __init__(self, dirname):
        self.olddir = os.getcwd()
        os.chdir(dirname)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        os.chdir(self.olddir)


class PhysicalDiskMounts:

    """This class is a better psutil.disk_partitions()"""

    class Entry:

        def __init__(self, p):
            self.dev = p.device
            self.mount_point = p.mountpoint
            self.fs_type = p.fstype
            self.mnt_opts = p.opts

        @property
        def mnt_opt_list(self):
            return self.mnt_opts.split(",")

    class NotFoundError(Exception):
        pass

    @classmethod
    def get_entries(cls):
        return [cls.Entry(p) for p in psutil.disk_partitions()]

    @classmethod
    def find_root_entry(cls):
        ret = cls.find_entry_by_mount_point("/")
        if ret is None:
            raise cls.NotFoundError("no rootfs mount point")
        else:
            return ret

    @classmethod
    def find_entry_by_mount_point(cls, mount_point_path):
        for p in psutil.disk_partitions():
            if p.mountpoint == mount_point_path:
                return cls.Entry(p)
        return None
