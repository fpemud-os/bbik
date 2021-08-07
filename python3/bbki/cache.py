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


class DistfilesCache:

    def __init__(self, bbki):
        self._bbki = bbki

    def findDeprecatedFiles(self, destructive=False):
        keepFiles = set()
        for repo in self._bbki.repositories:
            for itemType, itemName in repo.query_item_type_name():
                items = repo.get_items_by_type_name(itemType, itemName)
                if destructive:
                    items = [items[-1]]
                for item in items:
                    varDict = item.get_variables()
                    fnList = _get_distfiles(varDict.get("SRC_URI", ""), varDict.get("SRC_URI_GIT", ""))
                    keepFiles |= set(fnList)
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


def _get_distfiles(src_uri, src_uri_git):
    ret = []

    for line in src_uri.split("\n"):
        line = line.strip()
        if line != "":
            ret.append(os.path.basename(line))

    for line in src_uri_git.split("\n"):
        line = line.strip()
        if line != "":
            ret.append("git-src" + urlib.parse.urlparse(line).path)

    return ret
