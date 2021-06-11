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

class BuildTarget:

    def __init__(self):
        self._arch = None
        self._verstr = None

    @property
    def name(self):
        # string, eg: "linux-x86_64-3.9.11-gentoo-r1"
        return "linux-" + self._arch + "-" + self._verstr

    @property
    def postfix(self):
        # string, eg: "x86_64-3.9.11-gentoo-r1"
        return self._arch + "-" + self._verstr

    @property
    def arch(self):
        # string, eg: "x86_64".
        return self._arch

    @property
    def srcArch(self):
        if self._arch == "i386" or self._arch == "x86_64":
            return "x86"
        elif self._arch == "sparc32" or self._arch == "sparc64":
            return "sparc"
        elif self._arch == "sh":
            return "sh64"
        else:
            return self._arch

    @property
    def verstr(self):
        # string, eg: "3.9.11-gentoo-r1"
        return self._verstr

    @property
    def ver(self):
        # string, eg: "3.9.11"
        try:
            return self._verstr[:self._verstr.index("-")]
        except ValueError:
            return self._verstr

    @property
    def kernelFile(self):
        return "kernel-" + self.postfix

    @property
    def kernelCfgFile(self):
        return "config-" + self.postfix

    @property
    def kernelCfgRuleFile(self):
        return "config-" + self.postfix + ".rules"

    @property
    def kernelMapFile(self):
        return "System.map-" + self.postfix

    @property
    def kernelSrcSignatureFile(self):
        return "signature-" + self.postfix

    @property
    def initrdFile(self):
        return "initramfs-" + self.postfix

    @property
    def initrdTarFile(self):
        return "initramfs-files-" + self.postfix + ".tar.bz2"

    @staticmethod
    def newFromPostfix(postfix):
        partList = postfix.split("-")
        if len(partList) < 2:
            raise Exception("illegal postfix")

        bTarget = BuildTarget()
        bTarget._arch = partList[0]
        bTarget._verstr = "-".join(partList[1:])
        return bTarget

    @staticmethod
    def newFromKernelFilename(kernelFilename):
        """kernelFilename format: kernel-x86_64-3.9.11-gentoo-r1"""

        assert os.path.basename(kernelFilename) == kernelFilename

        partList = kernelFilename.split("-")
        if len(partList) < 3:
            raise Exception("illegal kernel file")
        if not FmUtil.isValidKernelArch(partList[1]):
            raise Exception("illegal kernel file")
        if not FmUtil.isValidKernelVer(partList[2]):
            raise Exception("illegal kernel file")

        bTarget = BuildTarget()
        bTarget._arch = partList[1]
        bTarget._verstr = "-".join(partList[2:])
        return bTarget

    @staticmethod
    def newFromKernelDir(hostArch, kernelDir):
        assert os.path.isabs(kernelDir)

        version = None
        patchlevel = None
        sublevel = None
        extraversion = None
        with open(os.path.join(kernelDir, "Makefile")) as f:
            buf = f.read()

            m = re.search("VERSION = ([0-9]+)", buf, re.M)
            if m is None:
                raise Exception("illegal kernel source directory")
            version = int(m.group(1))

            m = re.search("PATCHLEVEL = ([0-9]+)", buf, re.M)
            if m is None:
                raise Exception("illegal kernel source directory")
            patchlevel = int(m.group(1))

            m = re.search("SUBLEVEL = ([0-9]+)", buf, re.M)
            if m is None:
                raise Exception("illegal kernel source directory")
            sublevel = int(m.group(1))

            m = re.search("EXTRAVERSION = (\\S+)", buf, re.M)
            if m is not None:
                extraversion = m.group(1)

        bTarget = BuildTarget()
        bTarget._arch = hostArch
        if extraversion is not None:
            bTarget._verstr = "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
        else:
            bTarget._verstr = "%d.%d.%d" % (version, patchlevel, sublevel)
        return bTarget
