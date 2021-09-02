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
import pathlib
from ._po import BootMode


def get_boot_mode():
    if os.path.exists("/sys/firmware/efi"):
        return BootMode.EFI
    else:
        return BootMode.BIOS


def compare_kernel_config_files(file1, file2):
    # Returns True if two files are same
    return compare_kernel_config(pathlib.Path(file1).read_text(), pathlib.Path(file2).read_text())


def compare_kernel_config(content1, content2):
    # Returns True if two config are same

    lineList1 = content1.split("\n")
    lineList1 = [x for x in lineList1 if x.strip() != "" and not x.strip().startswith("#")]
    lineList1.sort()

    lineList2 = content2.split("\n")
    lineList2 = [x for x in lineList2 if x.strip() != "" and not x.strip().startswith("#")]
    lineList2.sort()

    if len(lineList1) != len(lineList2):
        return False
    for i in range(0, len(lineList1)):
        if lineList1[i] != lineList2[i]:
            return False
    return True


def compare_kernel_config_rules_files(file1, file2):
    # FIXME
    assert False


def compare_kernel_config_rules(content1, content2):
    # FIXME
    assert False
