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
import robust_layer.simple_fops


class Cleaner:

    def __init__(self, bbki, pretend=False):
        self._bbki = bbki
        self._bPretend = pretend

    def clean_boot_dir(self):
        hdir = self._bbki._fsLayout.get_boot_history_dir()
        if not os.path.exists(hdir):
            return []

        ret = []
        for fn in os.listdir(hdir):
            fullfn = os.path.join(hdir, fn)
            ret.append(fullfn)
            robust_layer.simple_fops.rm(fullfn)
        return sorted(ret)

    def clean_kernel_modules_dir(self):
        hdir = self._bbki._fsLayout.get_kernel_modules_dir()
        if not os.path.exists(hdir):
            return []

        cbe = self._bbki.get_current_boot_entry()
        pbe = self._bbki.get_pending_boot_entry()
        ret = []
        for fn in os.listdir(hdir):
            if cbe is not None and fn == cbe.verstr:
                continue
            if pbe is not None and fn == pbe.verstr:
                continue
            robust_layer.simple_fops.rm(fullfn)
            ret.append(os.path.join(hdir, fn))
        return sorted(ret)

    def findDeprecatedFiles(self, destructive=False):
        keepFiles = set()
        for repo in self._bbki.repositories:
            for atomType, atomName in repo.query_atom_type_name():
                items = repo.get_items_by_type_name(atomType, atomName)
                if destructive:
                    items = [items[-1]]
                for item in items:
                    keepFiles |= set([fn for t, r, fn in item.get_distfiles()])
        keepFiles.add("git-src")

        ret = []
        for fn in os.listdir(self._bbki.cache_distfiles_dir):
            if fn not in keepFiles:
                ret.append(fn)
                continue
            if fn == "git-src":
                for fn2 in os.listdir(os.path.join(self._bbki.cache_distfiles_dir, "git-src")):
                    fn2 = os.path.join("git-src", fn2)
                    if fn2 in keepFiles:
                        continue
                    ret.append(fn2)
                continue
        return ret














class KernelCleaner:

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


def _generateKernelCfgRulesFile(filename, *kargs):
    with open(filename, "w") as f:
        for kcfgRulesMap in kargs:
            for name, buf in kcfgRulesMap.items():
                f.write("## %s ######################\n" % (name))
                f.write("\n")
                f.write(buf)
                f.write("\n")
                f.write("\n")
                f.write("\n")










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

