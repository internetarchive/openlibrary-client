#!/usr/bin/env python

"""
    __init__.py
    ~~~~~~~~~~~

    :copyright: (c) 2016 by Internet Archive.
    :license: see LICENSE for more details.
"""

__title__ = 'olclient'
__version__ = '0.0.20'
__author__ = 'Internet Archive'


from .bots import AbstractBotJob
from .openlibrary import OpenLibrary
from .common import Book, Author
