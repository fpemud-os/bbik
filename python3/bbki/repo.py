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
import robust_layer.simple_git


class Repository:

    def __init__(self, bbki, path):
        self._bbki = bbki
        self._path = path

    def is_repo_exist(self):
        return os.path.exists(self._path)

    def get_repo_dir(self):
        return self._path

    def check(self, bAutoFix=False):
        if not self.is_repo_exist():
            if bAutoFix:
                self.create_repository()
            else:
                raise RepositoryCheckError("repository does not exist")

    def create(self):
        # Business exception should not be raise, but be printed as error message
        self.sync_repository()

    def sync(self):
        # Business exception should not be raise, but be printed as error message
        robust_layer.simple_git.pull(self._cfg.data_repo_dir, reclone_on_failure=True, url="https://github.com/fpemud-os/bbki-repo")


class KernelPackage:

    def __init__(self, repostory):
        pass

    




class KernelAddonPackage:

    def __init__(self, repostory):
        pass




class RepositoryCheckError(Exception):

    def __init__(self, message):
        self.message = message
