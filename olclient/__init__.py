#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    __init__.py
    ~~~~~~~~~~~

    :copyright: (c) 2016 by Internet Archive.
    :license: see LICENSE for more details.
"""

__title__ = 'olclient'
__version__ = '0.0.18'
__author__ = 'Internet Archive'


from .openlibrary import OpenLibrary
from .marc import MARC
from .common import Book, Author
