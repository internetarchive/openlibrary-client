#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    setup.py
    ~~~~~~~~

    :copyright: (c) 2016 by .
    :license: see LICENSE for more details.
"""

import codecs
import os
import re
from setuptools import setup


here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    """Taken from pypa pip setup.py:
    intentionally *not* adding an encoding option to open, See:
       https://github.com/pypa/virtualenv/issues/201#issuecomment-3145690
    """
    return codecs.open(os.path.join(here, *parts), 'r').read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def requirements():
    """Returns requirements.txt as a list usable by setuptools"""
    import os
    reqtxt = os.path.join(here, u'requirements.txt')
    with open(reqtxt) as f:
        return f.read().split()

setup(
    name='openlibrary-client',
    version=find_version("olclient", "__init__.py"),
    description=u'A python client for Open Library',
    long_description=read('README.md'),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4"
    ],
    author='Internet Archive',
    author_email='mek@archive.org',
    url='https://github.com/ArchiveLabs/openlibrary-client',
    include_package_data=True,
    packages=[
        'olclient',
        ],
    entry_points={
        'console_scripts': ['ol=olclient.cli:main'],
    },
    extras_require={
        ':python_version=="2.7"': ['argparse']
    },
    platforms='any',
    license='LICENSE',
    install_requires=requirements()
)
