#!/usr/bin/env python3

import sys
import subprocess
import distutils.util
from setuptools import setup, find_packages
from setuptools.command.install import install

# check Python's version
if sys.version_info < (3, 8):
    sys.stderr.write('This module requires at least Python 3.8\n')
    sys.exit(1)

# check linux platform
platform = distutils.util.get_platform()
if not platform.startswith('linux'):
    sys.stderr.write("This module is not available on %s\n" % platform)
    sys.exit(1)

classif = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: GPLv3 License',
    'Natural Language :: English',
    'Operating System :: POSIX :: Linux',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3.8',
    'Programming Language :: Python :: 3.9',
    'Topic :: Software Development :: Libraries :: Python Modules',
]

class custom_install(install):
    def run(self):
        self._compile_initramfs()
        super().run()

    def _compile_initramfs(self):
        subprocess.check_call('make', cwd='./python3/bbki/initramfs', shell=True)

# Do setup
setup(
    name='bbki',
    version='0.0.1',
    description='Manage BIOS, Bootloader, Kernel and Initramfs',
    author='Fpemud',
    author_email='fpemud@sina.com',
    license='GPLv3 License',
    platforms='Linux',
    classifiers=classif,
    url='http://github.com/fpemud/bbki',
    download_url='',
    packages=['bbki'],
    package_dir={
        'bbki': 'python3/bbki',
    },
    package_data={
        'bbki': ['kernel-config-rules/*', 'initramfs/init', 'initramfs/lvm-lv-activate', 'initramfs/*.c'],
    },
    cmdclass={
        'install': custom_install,
    },
)
