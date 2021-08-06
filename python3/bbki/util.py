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

import time
import subprocess


class Util:

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



class TempChdir:

    def __init__(self, dirname):
        self.olddir = os.getcwd()
        os.chdir(dirname)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        os.chdir(self.olddir)

