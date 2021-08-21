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

"""
bbki

@author: Fpemud
@license: GPLv3 License
@contact: fpemud@sina.com
"""

__author__ = "fpemud@sina.com (Fpemud)"
__version__ = "0.0.1"


from ._bbki import Bbki

from ._po import KernelType
from ._po import BootMode
from ._po import SystemInit
from ._po import SystemInitInfo
from ._po import RescueOsSpec
from ._po import HostInfo
from ._po import HostMountPoint
from ._po import HostDisk
from ._po import HostDiskLvmLv
from ._po import HostDiskBcache
from ._po import HostDiskScsiDisk
from ._po import HostDiskNvmeDisk
from ._po import HostDiskXenDisk
from ._po import HostDiskVirtioDisk
from ._po import HostDiskPartition
from ._po import HostAuxOs

from ._config import Config
from ._config import EtcDirConfig

from ._repo import Repo
from ._repo import RepoAtom

from ._boot_entry import BootEntry

from ._kernel import KernelInstaller
from ._kernel import KernelInstallProgress
