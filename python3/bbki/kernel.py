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
import robust_layer.wget
import robust_layer.simple_git
from . import Bbki
from .util import Util
from .util import TempChdir


class KernelInstaller:

    def __init__(self, bbki, kernel_config_rules):
        self._bbki = bbki

    def fetch_kernel(self, item):
        assert item.item_type == Bbki.ITEM_TYPE_KERNEL
        self._fetchItem(item)

    def fetch_kernel_addon(self, addon_item):
        assert addon_item.item_type == Bbki.ITEM_TYPE_KERNEL_ADDON
        self._fetchItem(addon_item)

    def extract_kernel(self, item):
        assert item.item_type == Bbki.ITEM_TYPE_KERNEL
        self._extractItem(item)

    def extract_kernel_addon(self, addon_item):
        assert addon_item.item_type == Bbki.ITEM_TYPE_KERNEL_ADDON
        self._extractItem(addon_item)

    def patch(self, addon_item_list):
        for addon_item in addon_item_list:
            assert addon_item.item_type == Bbki.ITEM_TYPE_KERNEL_ADDON
            addon_item.call_function("addon_patch_kernel")

    def generate_dotcfg(self):
        # head rules
        buf = ""
        if True:
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

            # android features need by anbox program
            if "anbox" in self._cfg.get_kernel_use_flag():
                buf += "[symbols:/Device drivers/Android]=y\n"
                buf += "STAGING=y\n"
                buf += "ASHMEM=y\n"
                buf += "\n"

            # debug feature
            if True:
                # killing CONFIG_VT is failed for now
                buf += "TTY=y\n"
                buf += "[symbols:VT]=y\n"
                buf += "[symbols:/Device Drivers/Graphics support/Console display driver support]=y\n"
                buf += "\n"
            if self.trickDebug:
                pass

            # symbols we dislike
            buf += "[debugging-symbols:/]=n\n"
            buf += "[deprecated-symbols:/]=n\n"
            buf += "[workaround-symbols:/]=n\n"
            buf += "[experimental-symbols:/]=n\n"
            buf += "[dangerous-symbols:/]=n\n"
            buf += "\n"

        # generate rules file
        self._generateKernelCfgRulesFile(self.kcfgRulesTmpFile,
                                         {"head": buf},
                                         self.kernelCfgRules)

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            Util.shellCall("/bin/sed -i '/VT=n/d' %s" % (self.kcfgRulesTmpFile))

        # generate the real ".config"
        Util.cmdCall("/usr/libexec/fpemud-os-sysman/bugfix-generate-dotcfgfile.py",
                       self.realSrcDir, self.kcfgRulesTmpFile, self.dotCfgFile)

        # "make olddefconfig" may change the .config file further
        self._makeAuxillary(self.realSrcDir, "olddefconfig")

    def build_kernel(self):
        pass

    def build_addon(self):
        pass

    def build_addons(self):
        pass

    def cleanup(self):
        pass




class Cleaner:

    def __init__(self):
        pass

    def get_files(self):



        if os.path.exists(self.historyDir):
            ret = []
            for fn in os.listdir(self.historyDir):
                ret.append(os.path.join(self.historyDir, fn))
            return ret
        else:
            return []











# get file list to be removed in boot directory
bootFileList = sorted(FkmBootDir().getHistoryFileList())

# get file list to be removed in kernel module directory
moduleFileList = []
if True:
    moduleFileList = os.listdir(kernelModuleDir)
    ret = FkmBootEntry.findCurrent()
    if ret is not None:
        moduleFileList.remove(ret.buildTarget.verstr)
    moduleFileList = sorted([os.path.join(kernelModuleDir, f) for f in moduleFileList])

# get file list to be removed in firmware directory
firmwareFileList = []
if os.path.exists(firmwareDir):
    validList = []
    for ver in os.listdir(kernelModuleDir):
        if ver in moduleFileList:
            continue
        verDir = os.path.join(kernelModuleDir, ver)
        for fullfn in glob.glob(os.path.join(verDir, "**", "*.ko"), recursive=True):
            # python-kmod bug: can only recognize the last firmware in modinfo
            # so use the command output of modinfo directly
            for line in FmUtil.cmdCall("/bin/modinfo", fullfn).split("\n"):
                m = re.fullmatch("firmware: +(\\S.*)", line)
                if m is None:
                    continue
                firmwareName = m.group(1)
                if not os.path.exists(os.path.join(firmwareDir, firmwareName)):
                    continue
                validList.append(firmwareName)

    standardFiles = [
        ".ctime",
        "regulatory.db",
        "regulatory.db.p7s",
    ]
    for root, dirs, files in os.walk(firmwareDir):
        for filepath in files:
            firmwareName = os.path.join(re.sub("^/lib/firmware/?", "", root), filepath)
            if firmwareName in standardFiles:
                continue
            if firmwareName in validList:
                continue
            firmwareFileList.append(firmwareName)

# show file list to be removed in boot directory
print("            Items to be removed in \"/boot\":")
if len(bootFileList) == 0:
    print("              None")
else:
    for f in bootFileList:
        print("              %s" % (f))

# show file list to be removed in kernel module directory
print("            Items to be removed in \"%s\":" % (kernelModuleDir))
if len(moduleFileList) == 0:
    print("              None")
else:
    for f in moduleFileList:
        assert os.path.isdir(os.path.join(kernelModuleDir, f))
        print("              %s/" % (f))

# show file list to be removed in firmware directory
print("            Items to be removed in \"%s\":" % (firmwareDir))
if len(firmwareFileList) == 0:
    print("              None")
else:
    for f in firmwareFileList:
        print("              %s" % (f))

# remove files
if len(bootFileList) > 0 or len(moduleFileList) > 0 or len(firmwareFileList) > 0:
    ret = 1
    print("        - Deleting...")
    for f in bootFileList:
        robust_layer.simple_fops.rm(os.path.join(bootDir, f))
    for f in moduleFileList:
        robust_layer.simple_fops.rm(os.path.join(kernelModuleDir, f))
    for f in firmwareFileList:
        fullfn = os.path.join(firmwareDir, f)
        robust_layer.simple_fops.rm(os.path.join(firmwareDir, f))
        d = os.path.dirname(fullfn)
        if len(os.listdir(d)) == 0:
            os.rmdir(d)
else:
    ret = 0



























class KernelBuilder:

    def __init__(self, bbki_config, kcache_path, patch_path, kernel_config_rules, temp_directory):
        assert len(os.listdir(temp_directory)) == 0

        self._cfg = bbki_config
        self.kcache = DistfilesCache(kcache_path, patch_path)

        self.kernelCfgRules = kernel_config_rules

        self.tmpDir = temp_directory
        self.ksrcTmpDir = os.path.join(self.tmpDir, "ksrc")
        self.firmwareTmpDir = os.path.join(self.tmpDir, "firmware")
        self.wirelessRegDbTmpDir = os.path.join(self.tmpDir, "wireless-regdb")
        self.kcfgRulesTmpFile = os.path.join(self.tmpDir, "kconfig.rules")

        self.kernelVer = self.kcache.getLatestKernelVersion()
        self.firmwareVer = self.kcache.getLatestFirmwareVersion()
        self.wirelessRegDbVer = self.kcache.getLatestWirelessRegDbVersion()

        self.kernelFile = self.kcache.getKernelFileByVersion(self.kernelVer)
        if not os.path.exists(self.kernelFile):
            raise Exception("\"%s\" does not exist" % (self.kernelFile))

        self.firmwareFile = self.kcache.getFirmwareFileByVersion(self.firmwareVer)
        if not os.path.exists(self.firmwareFile):
            raise Exception("\"%s\" does not exist" % (self.firmwareFile))

        self.wirelessRegDbFile = self.kcache.getWirelessRegDbFileByVersion(self.wirelessRegDbVer)
        if not os.path.exists(self.wirelessRegDbFile):
            raise Exception("\"%s\" does not exist" % (self.wirelessRegDbFile))

        self.realSrcDir = None
        self.dotCfgFile = None
        self.dstTarget = None
        self.srcSignature = None

        # trick: kernel debug is seldomly needed
        self.trickDebug = False

    def extract(self):
        # extract kernel source
        os.makedirs(self.ksrcTmpDir)
        Util.cmdCall("/bin/tar", "-xJf", self.kernelFile, "-C", self.ksrcTmpDir)
        realSrcDir = os.path.join(self.ksrcTmpDir, os.listdir(self.ksrcTmpDir)[0])

        # patch kernel source
        for name in self.kcache.getPatchList():
            fullfn = self.kcache.getPatchExecFile(name)
            out = None
            with TempChdir(realSrcDir):
                assert fullfn.endswith(".py")
                out = Util.cmdCall("python3", fullfn)     # FIXME, should respect shebang
            if out == "outdated":
                print("WARNING: Kernel patch \"%s\" is outdated." % (name))
            elif out == "":
                pass
            else:
                raise Exception("Kernel patch \"%s\" exits with error \"%s\"." % (name, out))

        # extract kernel firmware
        os.makedirs(self.firmwareTmpDir)
        Util.cmdCall("/bin/tar", "-xJf", self.firmwareFile, "-C", self.firmwareTmpDir)

        # extract wireless regulatory database
        os.makedirs(self.wirelessRegDbTmpDir)
        Util.cmdCall("/bin/tar", "-xJf", self.wirelessRegDbFile, "-C", self.wirelessRegDbTmpDir)

        # get real source directory
        self.realSrcDir = realSrcDir
        self.dotCfgFile = os.path.join(self.realSrcDir, ".config")
        self.dstTarget = BuildTarget.new_from_kernel_srcdir(Util.getHostArch(), self.realSrcDir)

        # calculate source signature
        self.srcSignature = "kernel: %s\n" % (Util.hashDir(self.realSrcDir))
        for name in self.kcache.getExtraDriverList():
            sourceDir = self.kcache.getExtraDriverSourceDir(name)
            self.srcSignature += "edrv-src-%s: %s\n" % (name, Util.hashDir(sourceDir))

    def buildStepGenerateDotCfg(self):
        # head rules
        buf = ""
        if True:
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

            # android features need by anbox program
            if "anbox" in self._cfg.get_kernel_use_flag():
                buf += "[symbols:/Device drivers/Android]=y\n"
                buf += "STAGING=y\n"
                buf += "ASHMEM=y\n"
                buf += "\n"

            # debug feature
            if True:
                # killing CONFIG_VT is failed for now
                buf += "TTY=y\n"
                buf += "[symbols:VT]=y\n"
                buf += "[symbols:/Device Drivers/Graphics support/Console display driver support]=y\n"
                buf += "\n"
            if self.trickDebug:
                pass

            # symbols we dislike
            buf += "[debugging-symbols:/]=n\n"
            buf += "[deprecated-symbols:/]=n\n"
            buf += "[workaround-symbols:/]=n\n"
            buf += "[experimental-symbols:/]=n\n"
            buf += "[dangerous-symbols:/]=n\n"
            buf += "\n"

        # generate rules file
        self._generateKernelCfgRulesFile(self.kcfgRulesTmpFile,
                                         {"head": buf},
                                         self.kernelCfgRules)

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            Util.shellCall("/bin/sed -i '/VT=n/d' %s" % (self.kcfgRulesTmpFile))
        if self.trickDebug:
            Util.shellCall("/bin/sed -i 's/=m,y/=y/g' %s" % (self.kcfgRulesTmpFile))
            Util.shellCall("/bin/sed -i 's/=m/=y/g' %s" % (self.kcfgRulesTmpFile))

        # generate the real ".config"
        Util.cmdCall("/usr/libexec/fpemud-os-sysman/bugfix-generate-dotcfgfile.py",
                       self.realSrcDir, self.kcfgRulesTmpFile, self.dotCfgFile)

        # "make olddefconfig" may change the .config file further
        self._makeAuxillary(self.realSrcDir, "olddefconfig")

    def buildStepMakeInstall(self):
        self._makeMain(self.realSrcDir)
        Util.cmdCall("/bin/cp", "-f",
                       "%s/arch/%s/boot/bzImage" % (self.realSrcDir, self.dstTarget.arch),
                       os.path.join(_bootDir, self.dstTarget.kernelFile))
        Util.cmdCall("/bin/cp", "-f",
                       "%s/System.map" % (self.realSrcDir),
                       os.path.join(_bootDir, self.dstTarget.kernelMapFilename))
        Util.cmdCall("/bin/cp", "-f",
                       "%s/.config" % (self.realSrcDir),
                       os.path.join(_bootDir, self.dstTarget.kernel_config_filename))
        Util.cmdCall("/bin/cp", "-f",
                       self.kcfgRulesTmpFile,
                       os.path.join(_bootDir, self.dstTarget.kernel_config_rules_filename))

        self._makeAuxillary(self.realSrcDir, "modules_install")

    def buildStepInstallFirmware(self):
        # get add all *used* firmware file
        # FIXME:
        # 1. should consider built-in modules by parsing /lib/modules/X.Y.Z/modules.builtin.modinfo
        # 2. currently it seems built-in modules don't need firmware
        firmwareList = []
        for fullfn in glob.glob(os.path.join("/lib/modules", self.dstTarget.verstr, "**", "*.ko"), recursive=True):
            # python-kmod bug: can only recognize the last firmware in modinfo
            # so use the command output of modinfo directly
            for line in Util.cmdCall("/bin/modinfo", fullfn).split("\n"):
                m = re.fullmatch("firmware: +(\\S.*)", line)
                if m is not None:
                    firmwareList.append((m.group(1), fullfn.replace("/lib/modules/%s/" % (self.dstTarget.verstr), "")))

        # copy firmware from official firmware repository
        os.makedirs("/lib/firmware", exist_ok=True)
        for fn, kn in firmwareList:
            srcFn = os.path.join(self.firmwareTmpDir, fn)
            dstFn = os.path.join("/lib/firmware", fn)
            if os.path.exists(srcFn):
                os.makedirs(os.path.dirname(dstFn), exist_ok=True)
                shutil.copy(srcFn, dstFn)

        # copy firmware from extra firmware repositories
        if True:
            usedExtraNames = set()
            for fn, kn in firmwareList:
                dstFn = os.path.join("/lib/firmware", fn)
                for firmwareName in self.kcache.getExtraFirmwareList():
                    fullfn, bOverWrite = self.kcache.getExtraFirmwareFileMapping(firmwareName, fn)
                    if fullfn is None:
                        continue
                    if os.path.exists(dstFn) and not bOverWrite:
                        continue
                    os.makedirs(os.path.dirname(dstFn), exist_ok=True)
                    shutil.copy(fullfn, dstFn)
                    usedExtraNames.add(firmwareName)
            for firmwareName in set(self.kcache.getExtraFirmwareList()) - usedExtraNames:
                print("WARNING: Extra firmware \"%s\" is outdated." % (firmwareName))

        # copy wireless-regdb
        if True:
            ret = glob.glob(os.path.join(self.wirelessRegDbTmpDir, "**", "regulatory.db"), recursive=True)
            assert len(ret) == 1
            shutil.copy(ret[0], "/lib/firmware")
        if True:
            ret = glob.glob(os.path.join(self.wirelessRegDbTmpDir, "**", "regulatory.db.p7s"), recursive=True)
            assert len(ret) == 1
            shutil.copy(ret[0], "/lib/firmware")

        # ensure corrent permission
        Util.shellCall("/usr/bin/find /lib/firmware -type f | xargs chmod 644")
        Util.shellCall("/usr/bin/find /lib/firmware -type d | xargs chmod 755")

        # record
        with open("/lib/firmware/.ctime", "w") as f:
            f.write(self.firmwareVer + "\n")
            f.write(self.wirelessRegDbVer + "\n")

    def buildStepBuildAndInstallExtraDriver(self, driverName):
        cacheDir = self.kcache.getExtraDriverSourceDir(driverName)
        fullfn = self.kcache.getExtraDriverExecFile(driverName)
        buildTmpDir = os.path.join(self.tmpDir, driverName)
        os.mkdir(buildTmpDir)
        with TempChdir(buildTmpDir):
            assert fullfn.endswith(".py")
            Util.cmdExec("python3", fullfn, cacheDir, self.kernelVer)     # FIXME, should respect shebang

    def buildStepClean(self):
        with open(os.path.join(_bootDir, self.dstTarget.kernelSrcSignatureFile), "w") as f:
            f.write(self.srcSignature)
        os.unlink(os.path.join(self._getModulesDir(), "source"))
        os.unlink(os.path.join(self._getModulesDir(), "build"))

    def _getModulesDir(self):
        return "/lib/modules/%s" % (self.kernelVer)

    def _makeMain(self, dirname, envVarList=[]):
        optList = []

        # CFLAGS
        optList.append("CFLAGS=\"-Wno-error\"")

        # from /etc/portage/make.conf
        optList.append(Util.getMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS"))

        # from envVarList
        optList += envVarList

        # execute command
        with TempChdir(dirname):
            Util.shellCall("/usr/bin/make %s" % (" ".join(optList)))

    def _makeAuxillary(self, dirname, target, envVarList=[]):
        with TempChdir(dirname):
            Util.shellCall("/usr/bin/make %s %s" % (" ".join(envVarList), target))

    def _generateKernelCfgRulesFile(self, filename, *kargs):
        with open(filename, "w") as f:
            for kcfgRulesMap in kargs:
                for name, buf in kcfgRulesMap.items():
                    f.write("## %s ######################\n" % (name))
                    f.write("\n")
                    f.write(buf)
                    f.write("\n")
                    f.write("\n")
                    f.write("\n")
