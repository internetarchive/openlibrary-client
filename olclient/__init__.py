#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    __init__.py
    ~~~~~~~~~~~

    :copyright: (c) 2016 by Internet Archive.
    :license: see LICENSE for more details.
"""

__title__ = 'olclient'
__version__ = '0.0.1'
__author__ = 'Internet Archive'
__desc__ = 'A python client for Open Library'

from .openlibrary import OpenLibrary, Work, Results
from .marc import MARC
