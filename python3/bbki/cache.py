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
import configparser
from util import Util


class SyncRecord:
    
    def __init__(self, sync_record_filename):
        self.ksyncFile = sync_record_filename

    def _readDataFromKsyncFile(self, prefix):
        indexDict = {
            "kernel": 0,
            "firmware": 1,
            "wireless-regdb": 2,
        }
        with open(self.ksyncFile, "r") as f:
            return f.read().split("\n")[indexDict[prefix]]



class KCache:

    def __init__(self, bbki_config, patch_path, cache_path):
        self._cfg = bbki_config

        self.kcachePath = cache_path

        # ksync
        self.ksyncFile = os.path.join(self.kcachePath, "ksync.txt")

        # kernel patch information
        self.patchDir = os.path.join(patch_path, "patch")

        # extra kernel drivers
        # FIXME: check
        self.extraDriverDir = os.path.join(patch_path, "driver")
        self.extraDriverDict = dict()
        for fn in os.listdir(self.extraDriverDir):
            self.extraDriverDict[fn] = self._parseExtraDriver(fn, os.path.join(self.extraDriverDir, fn))

        # extra firmwares
        # FIXME: check
        self.extraFirmwareDir = os.path.join(patch_path, "firmware")
        self.extraFirmwareDict = dict()
        for fn in os.listdir(self.extraFirmwareDir):
            name = re.sub(r'\.ini$', "", fn)
            assert name != fn
            self.extraFirmwareDict[name] = self._parseExtraFirmware(name, os.path.join(self.extraFirmwareDir, fn))

    def getPatchList(self):
        # FIXME: other extension
        return [re.sub(r'\.py$', "", x) for x in os.listdir(self.patchDir)]

    def getExtraDriverList(self):
        return list(self.extraDriverDict.keys())

    def getExtraFirmwareList(self):
        return list(self.extraFirmwareDict.keys())

    def getLatestKernelVersion(self):
        kernelVer = self._readDataFromKsyncFile("kernel")
        kernelVer = self._cfg.check_version_mask("kernel", kernelVer)
        return kernelVer

    def getKernelFileByVersion(self, version):
        """returns absolute file path"""

        fn = "linux-" + version + ".tar.xz"
        fn = os.path.join(self.kcachePath, fn)
        return fn

    def getLatestFirmwareVersion(self):
        # firmware version is the date when it is generated
        # example: 2019.06.03

        ret = self._readDataFromKsyncFile("firmware")
        ret = self._cfg.check_version_mask("firmware", ret)
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
        ret = self._cfg.check_version_mask("wireless-regdb", ret)
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
                if Util.compareVersion(f.replace("linux-", "").replace(".tar.xz", ""), cbe.buildTarget.verstr) < 0:
                    kernelFileList.append(f)    # remove lower version
            elif f.startswith("linux-") and f.endswith(".tar.sign") and not f.startswith("linux-firmware-"):
                if Util.compareVersion(f.replace("linux-", "").replace(".tar.sign", ""), cbe.buildTarget.verstr) < 0:
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


