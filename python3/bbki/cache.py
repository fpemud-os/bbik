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
import robust_layer
import configparser
import lxml.html
import urllib.request
from util import Util


class KernelSyncer:
    
    @staticmethod
    def get_latest_version():
        kernelUrl = "https://www.kernel.org"
        typename = "stable"
        while True:
            # get kernel version from internet
            try:
                with urllib.request.urlopen(kernelUrl, timeout=robust_layer.TIMEOUT) as resp:
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
            except OSError as e:
                print("Failed to acces %s, %s" % (kernelUrl, e))
                time.sleep(robust_layer.RETRY_TIMEOUT)

    def __init__(self, bbki_config):
        self._cfg = bbki_config

    def sync(self):
        assert False


class FirmwareSyncer:

    @staticmethod
    def get_latest_version():
        firmwareUrl = "https://www.kernel.org/pub/linux/kernel/firmware"
        while True:
            # get firmware version version from internet
            try:
                ret = None
                with urllib.request.urlopen(firmwareUrl, timeout=robust_layer.TIMEOUT) as resp:
                    root = lxml.html.parse(resp)
                    for atag in root.xpath(".//a"):
                        m = re.fullmatch("linux-firmware-(.*)\\.tar\\.xz", atag.text)
                        if m is not None:
                            if ret is None or ret < m.group(1):
                                ret = m.group(1)
                    assert ret is not None
                return ret
            except OSError as e:
                print("Failed to acces %s, %s" % (firmwareUrl, e))
                time.sleep(robust_layer.RETRY_TIMEOUT)

    def __init__(self, bbki_config):
        self._cfg = bbki_config

    def sync(self):
        assert False


class ExtSourceSyncer:

    def __init__(self, bbki_config):
        self._cfg = bbki_config

    def sync(self):
        assert False


class WirelessRegdbSyncer:

    @staticmethod
    def get_latest_version():
        wirelessRegDbDirUrl = "https://www.kernel.org/pub/software/network/wireless-regdb"
        while True:
            try:
                ver = None
                with urllib.request.urlopen(wirelessRegDbDirUrl, timeout=robust_layer.TIMEOUT) as resp:
                    out = resp.read().decode("iso8859-1")
                    for m in re.finditer("wireless-regdb-([0-9]+\\.[0-9]+\\.[0-9]+)\\.tar\\.xz", out, re.M):
                        if ver is None or m.group(1) > ver:
                            ver = m.group(1)
                return ver
            except OSError as e:
                print("Failed to acces %s, %s" % (wirelessRegDbDirUrl, e))
                time.sleep(robust_layer.RETRY_TIMEOUT)

    def __init__(self, bbki_config):
        self._cfg = bbki_config

    def sync(self):
        assert False


class SyncRecord:
    
    def __init__(self, bbki_config):
        self._cfg = bbki_config

    def read(self, record_type):
        indexDict = {
            "kernel": 0,
            "firmware": 1,
            "wireless-regdb": 2,
        }
        with open(self._cfg.cache_sync_record_file, "r") as f:
            return f.read().split("\n")[indexDict[record_type]]

    def write(self, record_type, *kargs):
        vlist = ["", "", "", ""]
        if os.path.exists(self._cfg.cache_sync_record_file):
            with open(self._cfg.cache_sync_record_file) as f:
                vlist = f.read().split("\n")[0:3]
                while len(vlist) < 4:
                    vlist.append("")

        if record_type == "kernel":
            vlist[0] = kargs[0]
        elif record_type == "firmware":
            vlist[1] = kargs[0]
        elif record_type == "wireless-regdb":
            vlist[2] = kargs[0]
        else:
            assert False

        with open(self._cfg.cache_sync_record_file, "w") as f:
            for v in vlist:
                f.write(v + "\n")


class DistfilesCache:

    def __init__(self, bbki_config, patch_path, cache_path):
        self._cfg = bbki_config
        self._syncRecord = SyncRecord(self._cfg.cache_sync_record_file)

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
        kernelVer = self._syncRecord.read("kernel")
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

        ret = self._syncRecord.read("firmware")
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

        ret = self._syncRecord.read("wireless-regdb")
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


