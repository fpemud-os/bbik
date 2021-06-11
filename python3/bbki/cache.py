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
import io
import gzip
import time
import glob
import shutil
import configparser
import robust_layer
import robust_layer.simple_git
import robust_layer.simple_subversion
import lxml.html
import urllib.request
import urllib.error
from fm_util import FmUtil
from fm_util import TempChdir
from fm_util import TmpHttpDirFs
from fm_param import FmConst


class KCache:

    def __init__(self, cache_path, patch_path):
        self.kcachePath = cache_path
        self.patchPath = patch_path

        # ksync
        self.ksyncFile = os.path.join(self.kcachePath, "ksync.txt")

        # kernel information
        self.kernelUrl = "https://www.kernel.org"

        # firmware information
        self.firmwareUrl = "https://www.kernel.org/pub/linux/kernel/firmware"

        # kernel patch information
        self.patchDir = os.path.join(self.patchPath, "patch")

        # extra kernel drivers
        # FIXME: check
        self.extraDriverDir = os.path.join(self.patchPath, "driver")
        self.extraDriverDict = dict()
        for fn in os.listdir(self.extraDriverDir):
            self.extraDriverDict[fn] = self._parseExtraDriver(fn, os.path.join(self.extraDriverDir, fn))

        # extra firmwares
        # FIXME: check
        self.extraFirmwareDir = os.path.join(self.patchPath, "firmware")
        self.extraFirmwareDict = dict()
        for fn in os.listdir(self.extraFirmwareDir):
            name = re.sub(r'\.ini$', "", fn)
            assert name != fn
            self.extraFirmwareDict[name] = self._parseExtraFirmware(name, os.path.join(self.extraFirmwareDir, fn))

        # wireless-regdb
        self.wirelessRegDbDirUrl = "https://www.kernel.org/pub/software/network/wireless-regdb"

    def sync(self):
        # get kernel version from internet
        if True:
            while True:
                ver = self._findKernelVersion("stable")
                if ver is not None:
                    self._writeKsyncFile("kernel", ver)
                    break
                time.sleep(1.0)
            print("Linux kernel: %s" % (self.getLatestKernelVersion()))

        # get firmware version version from internet
        if True:
            while True:
                ver = self._findFirmwareVersion()
                if ver is not None:
                    self._writeKsyncFile("firmware", ver)
                    break
                time.sleep(1.0)
            print("Firmware: %s" % (self.getLatestFirmwareVersion()))

        # get wireless-regulatory-database version from internet
        if True:
            while True:
                ver = self._findWirelessRegDbVersion()
                if ver is not None:
                    self._writeKsyncFile("wireless-regdb", ver)
                    break
                time.sleep(1.0)
            print("Wireless Regulatory Database: %s" % (self.getLatestWirelessRegDbVersion()))

    def getPatchList(self):
        # FIXME: other extension
        return [re.sub(r'\.py$', "", x) for x in os.listdir(self.patchDir)]

    def getExtraDriverList(self):
        return list(self.extraDriverDict.keys())

    def getExtraFirmwareList(self):
        return list(self.extraFirmwareDict.keys())

    def updateKernelCache(self, kernelVersion):
        kernelFile = "linux-%s.tar.xz" % (kernelVersion)
        signFile = "linux-%s.tar.sign" % (kernelVersion)
        myKernelFile = os.path.join(self.kcachePath, kernelFile)
        mySignFile = os.path.join(self.kcachePath, signFile)

        # we already have the latest linux kernel?
        if os.path.exists(myKernelFile):
            if os.path.exists(mySignFile):
                print("File already downloaded.")
                return
            else:
                FmUtil.forceDelete(myKernelFile)
                FmUtil.forceDelete(mySignFile)

        # get mirror
        mr, retlist = FmUtil.portageGetLinuxKernelMirror(FmConst.portageCfgMakeConf,
                                                         FmConst.defaultKernelMirror,
                                                         kernelVersion,
                                                         [kernelFile, signFile])
        kernelFile = retlist[0]
        signFile = retlist[1]

        # download the target file
        FmUtil.wgetDownload("%s/%s" % (mr, kernelFile), myKernelFile)
        FmUtil.wgetDownload("%s/%s" % (mr, signFile), mySignFile)

    def updateFirmwareCache(self, firmwareVersion):
        firmwareFile = "linux-firmware-%s.tar.xz" % (firmwareVersion)
        signFile = "linux-firmware-%s.tar.sign" % (firmwareVersion)
        myFirmwareFile = os.path.join(self.kcachePath, firmwareFile)
        mySignFile = os.path.join(self.kcachePath, signFile)

        # we already have the latest firmware?
        if os.path.exists(myFirmwareFile):
            if os.path.exists(mySignFile):
                print("File already downloaded.")
                return
            else:
                FmUtil.forceDelete(myFirmwareFile)
                FmUtil.forceDelete(mySignFile)

        # get mirror
        mr, retlist = FmUtil.portageGetLinuxFirmwareMirror(FmConst.portageCfgMakeConf,
                                                           FmConst.defaultKernelMirror,
                                                           [firmwareFile, signFile])
        firmwareFile = retlist[0]
        signFile = retlist[1]

        # download the target file
        FmUtil.wgetDownload("%s/%s" % (mr, firmwareFile), myFirmwareFile)
        FmUtil.wgetDownload("%s/%s" % (mr, signFile), mySignFile)

    def updateExtraSourceCache(self, sourceInfo):
        cacheDir = os.path.join(self.kcachePath, "source-%s" % (sourceInfo["name"]))

        # source type "git"
        if sourceInfo["update-method"] == "git":
            robust_layer.simple_git.pull(cacheDir, reclone_on_failure=True, url=sourceInfo["url"])
            return

        # source type "svn"
        if sourceInfo["update-method"] == "svn":
            robust_layer.simple_subversion.update(cacheDir, recheckout_on_failure=True, url=sourceInfo["url"])
            return

        # source type "httpdir"
        if sourceInfo["update-method"] == "httpdir":
            fnList = []
            with TmpHttpDirFs(sourceInfo["url"]) as mp:
                fnList = os.listdir(mp.mountpoint)
            if sourceInfo["filter-regex"] != "":
                fnList = [x for x in fnList if re.fullmatch(sourceInfo["filter-regex"], x) is not None]
            if len(fnList) == 0:
                raise Exception("no file avaiable")
            remoteFullFn = os.path.join(sourceInfo["url"], fnList[-1])
            localFullFn = os.path.join(cacheDir, fnList[-1])
            if os.path.exists(localFullFn):
                print("File already downloaded.")
                return
            FmUtil.wgetDownload(remoteFullFn, localFullFn)
            for fn in os.listdir(cacheDir):
                fullfn = os.path.join(cacheDir, fn)
                if fullfn != localFullFn:
                    FmUtil.forceDelete(fullfn)
            return

        # source type "exec"
        if sourceInfo["update-method"] == "exec":
            fullfn = os.path.join(sourceInfo["selfdir"], sourceInfo["executable"])
            os.makedirs(cacheDir, exist_ok=True)
            with TempChdir(cacheDir):
                assert fullfn.endswith(".py")
                FmUtil.cmdExec("python3", fullfn)     # FIXME, should respect shebang
            return

        # invalid source type
        assert False

    def updateWirelessRegDbCache(self, wirelessRegDbVersion):
        filename = "wireless-regdb-%s.tar.xz" % (wirelessRegDbVersion)
        localFile = os.path.join(self.kcachePath, filename)

        # we already have the latest wireless regulatory database?
        if os.path.exists(localFile):
            print("File already downloaded.")
            return

        # download the target file
        FmUtil.wgetDownload("%s/%s" % (self.wirelessRegDbDirUrl, filename), localFile)

    def getLatestKernelVersion(self):
        kernelVer = self._readDataFromKsyncFile("kernel")
        kernelVer = self._versionMaskCheck("kernel", kernelVer)
        return kernelVer

    def getKernelFileByVersion(self, version):
        """returns absolute file path"""

        fn = "linux-" + version + ".tar.xz"
        fn = os.path.join(self.kcachePath, fn)
        return fn

    def getKernelUseFlags(self):
        """returns list of USE flags"""

        ret = set()
        for fn in os.listdir(FmConst.kernelUseDir):
            for line in FmUtil.readListFile(os.path.join(FmConst.kernelUseDir, fn)):
                line = line.replace("\t", " ")
                line2 = ""
                while line2 != line:
                    line2 = line
                    line = line.replace("  ", " ")
                for item in line.split(" "):
                    if item.startswith("-"):
                        item = item[1:]
                        ret.remove(item)
                    else:
                        ret.add(item)
        return sorted(list(ret))

    def getLatestFirmwareVersion(self):
        # firmware version is the date when it is generated
        # example: 2019.06.03

        ret = self._readDataFromKsyncFile("firmware")
        ret = self._versionMaskCheck("firmware", ret)
        return ret

    def getFirmwareFileByVersion(self, version):
        """returns absolute file path"""

        fn = "linux-firmware-" + version + ".tar.xz"
        fn = os.path.join(self.kcachePath, fn)
        return fn

    def getPatchExecFile(self, patchName):
        return os.path.join(self.patchDir, "patch", patchName + ".py")

    def getExtraDriverSourceInfo(self, driverName):
        return self.extraDriverDict[driverName]["source"]

    def getExtraDriverSourceDir(self, driverName):
        sourceInfo = self.getExtraDriverSourceInfo(driverName)
        return os.path.join(self.kcachePath, "source-%s" % (sourceInfo["name"]))

    def getExtraDriverExecFile(self, driverName):
        return os.path.join(self.patchDir, "driver", driverName, "build.py")

    def getExtraFirmwareSourceInfo(self, firmwareName):
        return self.extraFirmwareDict[firmwareName]["source"]

    def getExtraFirmwareSourceDir(self, firmwareName):
        sourceInfo = self.getExtraFirmwareSourceInfo(firmwareName)
        return os.path.join(self.kcachePath, "source-%s" % (sourceInfo["name"]))

    def getExtraFirmwareFileMapping(self, firmwareName, filePath):
        # return (realFullFilePath, bOverWrite)

        obj = self.extraFirmwareDict[firmwareName]["file-mapping-overwrite"]
        if filePath in obj:
            ret = os.path.join(self.getExtraFirmwareSourceDir(firmwareName), obj[filePath])
            assert os.path.exists(ret)
            return (ret, True)

        obj = self.extraFirmwareDict[firmwareName]["file-mapping-overwrite-regex"]
        for pattern in obj.keys():
            m = re.fullmatch(pattern, filePath)
            if m is None:
                continue
            ret = obj[pattern]
            ret = ret.replace("$0", m.group(0))
            i = 1
            for v in m.groups():
                ret = ret.replace("$%d" % (i), v)
                i += 1
            ret = os.path.join(self.getExtraFirmwareSourceDir(firmwareName), ret)       # change to full filename
            if not os.path.exists(ret):
                continue
            return (ret, True)

        obj = self.extraFirmwareDict[firmwareName]["file-mapping"]
        if filePath in obj:
            ret = os.path.join(self.getExtraFirmwareSourceDir(firmwareName), obj[filePath])
            assert os.path.exists(ret)
            return (ret, False)

        obj = self.extraFirmwareDict[firmwareName]["file-mapping-regex"]
        for pattern in obj.keys():
            m = re.fullmatch(pattern, filePath)
            if m is None:
                continue
            ret = obj[pattern]
            ret = ret.replace("$0", m.group(0))
            i = 1
            for v in m.groups():
                ret = ret.replace("$%d" % (i), v)
                i += 1
            ret = os.path.join(self.getExtraFirmwareSourceDir(firmwareName), ret)       # change to full filename
            if not os.path.exists(ret):
                continue
            return (ret, True)

        return (None, None)

    def getLatestWirelessRegDbVersion(self):
        # wireless regulatory database version is the date when it is generated
        # example: 2019.06.03

        ret = self._readDataFromKsyncFile("wireless-regdb")
        ret = self._versionMaskCheck("wireless-regdb", ret)
        return ret

    def getWirelessRegDbFileByVersion(self, version):
        """returns absolute file path"""

        fn = "wireless-regdb-" + version + ".tar.xz"
        fn = os.path.join(self.kcachePath, fn)
        return fn

    def getOldKernelFileList(self, cbe):
        kernelFileList = []
        for f in os.listdir(self.kcachePath):
            if f.startswith("linux-") and f.endswith(".tar.xz") and not f.startswith("linux-firmware-"):
                if FmUtil.compareVersion(f.replace("linux-", "").replace(".tar.xz", ""), cbe.buildTarget.verstr) < 0:
                    kernelFileList.append(f)    # remove lower version
            elif f.startswith("linux-") and f.endswith(".tar.sign") and not f.startswith("linux-firmware-"):
                if FmUtil.compareVersion(f.replace("linux-", "").replace(".tar.sign", ""), cbe.buildTarget.verstr) < 0:
                    kernelFileList.append(f)    # remove lower version
        return sorted(kernelFileList)

    def getOldFirmwareFileList(self):
        fileList = []
        for f in os.listdir(self.kcachePath):
            if f.startswith("linux-firmware-") and f.endswith(".tar.xz"):
                fileList.append(f)
                fileList.append(f.replace(".xz", ".sign"))
        fileList = sorted(fileList)
        if len(fileList) > 0:
            fileList = fileList[:-2]
        return fileList

    def getOldWirelessRegDbFileList(self):
        fileList = []
        for f in os.listdir(self.kcachePath):
            if f.startswith("wireless-regdb-") and f.endswith(".tar.xz"):
                fileList.append(f)
        fileList = sorted(fileList)
        if len(fileList) > 0:
            fileList = fileList[:-1]
        return fileList

    def _readDataFromKsyncFile(self, prefix):
        indexDict = {
            "kernel": 0,
            "firmware": 1,
            "wireless-regdb": 2,
        }
        with open(self.ksyncFile, "r") as f:
            return f.read().split("\n")[indexDict[prefix]]

    def _versionMaskCheck(self, prefix, version):
        for fn in os.listdir(FmConst.kernelMaskDir):
            with open(os.path.join(FmConst.kernelMaskDir, fn), "r") as f:
                buf = f.read()
                m = re.search("^>%s-(.*)$" % (prefix), buf, re.M)
                if m is not None:
                    if version > m.group(1):
                        version = m.group(1)
        return version

    def _findKernelVersion(self, typename):
        try:
            resp = urllib.request.urlopen(self.kernelUrl, timeout=robust_layer.TIMEOUT)
            if resp.info().get('Content-Encoding') is None:
                fakef = resp
            elif resp.info().get('Content-Encoding') == 'gzip':
                fakef = io.BytesIO(resp.read())
                fakef = gzip.GzipFile(fileobj=fakef)
            else:
                assert False
            root = lxml.html.parse(fakef)

            td = root.xpath(".//td[text()='%s:']" % (typename))[0]
            td = td.getnext()
            while len(td) > 0:
                td = td[0]
            return td.text
        except Exception as e:
            print("Failed to acces %s, %s" % (self.kernelUrl, e))
            return None

    def _findFirmwareVersion(self):
        try:
            resp = urllib.request.urlopen(self.firmwareUrl, timeout=robust_layer.TIMEOUT)
            root = lxml.html.parse(resp)
            ret = None
            for atag in root.xpath(".//a"):
                m = re.fullmatch("linux-firmware-(.*)\\.tar\\.xz", atag.text)
                if m is not None:
                    if ret is None or ret < m.group(1):
                        ret = m.group(1)
            assert ret is not None
            return ret
        except Exception as e:
            print("Failed to acces %s, %s" % (self.firmwareUrl, e))
            return None

    def _findWirelessRegDbVersion(self):
        try:
            ver = None
            resp = urllib.request.urlopen(self.wirelessRegDbDirUrl, timeout=robust_layer.TIMEOUT)
            out = resp.read().decode("iso8859-1")
            for m in re.finditer("wireless-regdb-([0-9]+\\.[0-9]+\\.[0-9]+)\\.tar\\.xz", out, re.M):
                if ver is None or m.group(1) > ver:
                    ver = m.group(1)
            return ver
        except Exception as e:
            print("Failed to acces %s, %s" % (self.wirelessRegDbDirUrl, e))
            return None

    def _writeKsyncFile(self, key, *kargs):
        vlist = ["", "", "", ""]
        if os.path.exists(self.ksyncFile):
            with open(self.ksyncFile) as f:
                vlist = f.read().split("\n")[0:3]
                while len(vlist) < 4:
                    vlist.append("")

        if key == "kernel":
            vlist[0] = kargs[0]
        elif key == "firmware":
            vlist[1] = kargs[0]
        elif key == "wireless-regdb":
            vlist[2] = kargs[0]

        with open(self.ksyncFile, "w") as f:
            for v in vlist:
                f.write(v + "\n")

    def _parseExtraDriver(self, name, dir_path):
        ret = {}

        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(dir_path, "main.ini"))

        updateMethod = cfg.get("source", "update-method")
        if updateMethod == "git":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "git",
                "url": cfg.get("source", "url"),
            }
        elif updateMethod == "svn":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "svn",
                "url": cfg.get("source", "url"),
            }
        elif updateMethod == "httpdir":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "httpdir",
                "url": cfg.get("source", "url"),
                "filter-regex": cfg.get("source", "filter-regex", fallback=""),
            }
        elif updateMethod == "exec":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "exec",
                "executable": cfg.get("source", "executable"),
                "selfdir": dir_path,
            }
        else:
            raise Exception("invalid update-method \"%s\" in config file of extra kernel driver \"%s\"", (updateMethod, name))

        return ret

    def _parseExtraFirmware(self, name, file_path):
        ret = {}

        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(file_path))

        updateMethod = cfg.get("source", "update-method")
        if updateMethod == "git":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "git",
                "url": cfg.get("source", "url"),
            }
        elif updateMethod == "svn":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "svn",
                "url": cfg.get("source", "url"),
            }
        else:
            raise Exception("invalid update-method \"%s\" in config file of extra firmware \"%s\"", (updateMethod, name))

        for section in ["file-mapping", "file-mapping-overwrite", "file-mapping-regex", "file-mapping-overwrite-regex"]:
            ret[section] = dict()
            if cfg.has_section(section):
                for opt in cfg.options(section):
                    ret[section][opt] = cfg.get(section, opt)

        return ret



class FkmBootEntry:

    def __init__(self, buildTarget):
        self.buildTarget = buildTarget

    @property
    def kernelFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelFile)

    @property
    def kernelCfgFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelCfgFile)

    @property
    def kernelCfgRuleFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelCfgRuleFile)

    @property
    def kernelSrcSignatureFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelSrcSignatureFile)

    @property
    def kernelMapFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelMapFile)

    @property
    def initrdFile(self):
        return os.path.join(_bootDir, self.buildTarget.initrdFile)

    @property
    def initrdTarFile(self):
        return os.path.join(_bootDir, self.buildTarget.initrdTarFile)

    def kernelFilesExists(self):
        if not os.path.exists(self.kernelFile):
            return False
        if not os.path.exists(self.kernelCfgFile):
            return False
        if not os.path.exists(self.kernelCfgRuleFile):
            return False
        if not os.path.exists(self.kernelMapFile):
            return False
        if not os.path.exists(self.kernelSrcSignatureFile):
            return False
        return True

    def initrdFileExists(self):
        if not os.path.exists(self.initrdFile):
            return False
        if not os.path.exists(self.initrdTarFile):
            return False
        return True

    @staticmethod
    def findCurrent(strict=True):
        ret = [x for x in sorted(os.listdir(_bootDir)) if x.startswith("kernel-")]
        if ret == []:
            return None

        buildTarget = BuildTarget.newFromKernelFilename(ret[-1])
        cbe = FkmBootEntry(buildTarget)
        if strict:
            if not cbe.kernelFilesExists():
                return None
            if not cbe.initrdFileExists():
                return None
        return cbe



_bootDir = "/boot"
