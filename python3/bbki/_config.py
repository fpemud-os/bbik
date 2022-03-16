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


class ConfigBase:

    @property
    def data_repo_dir(self):
        raise NotImplementedError()

    @property
    def cache_distfiles_dir(self):
        raise NotImplementedError()

    @property
    def cache_distfiles_ro_dir_list(self):
        raise NotImplementedError()

    @property
    def tmp_dir(self):
        raise NotImplementedError()

    def get_build_variable(self, var_name):
        raise NotImplementedError()

    def get_kernel_type(self):
        raise NotImplementedError()

    def get_kernel_name(self):
        raise NotImplementedError()

    def get_kernel_addon_names(self):
        raise NotImplementedError()

    def get_initramfs_name(self):
        raise NotImplementedError()

    def get_system_init(self):
        raise NotImplementedError()

    def get_bootloader_extra_time(self):
        raise NotImplementedError()

    def get_kernel_extra_init_cmdline(self):
        raise NotImplementedError()

    def test_version_mask(self, item_fullname, item_verstr):
        raise NotImplementedError()

    def check_against_repositories(self, repositories, autofix, error_callback):
        raise NotImplementedError()
