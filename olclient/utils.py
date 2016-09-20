#-*- encoding: utf-8 -*-

"""General independent utilities"""

from __future__ import absolute_import, division, print_function

import datetime
import re

ALPHANUMERICS_RE = re.compile(r'([^\s\w])+')


def has_unicode(text):
    """Python 2.7 compatible method to check if text has non-encoded
    unicode in it

    Args:
        text (str or unicode)

    Usage:
        >>> has_unicode("Hello world!")
        False
        >>> has_unicode("👋 🌎 !")
        True
    """
    return not all(ord(char) < 128 for char in text)


def chunks(seq, chunk_size):
    """Returns a generator which yields contiguous chunks of the sequence
    of size (up to) `chunk_size`.

    Usage:
        >>> list(chunk([1,2,3,4], 2))
        [[1, 2], [3, 4]]
        >>> list(chunk([1,2,3,4,5], 2))
        [[1, 2], [3, 4], [5]]
    """
    def take(seq, n):
        for i in range(n):
            yield next(seq)

    if not hasattr(seq, 'next'):
        seq = iter(seq)
    while True:
        x = list(take(seq, chunk_size))
        if x:
            yield x
        else:
            break

def rm_punctuation(text):
    """Strips anything that is not an alphanumeric or space"""
    return ALPHANUMERICS_RE.sub('', text)

def parse_datetime(value):
    """Parses ISO datetime formatted string.::
        >>> parse_datetime("2009-01-02T03:04:05.006789")
        datetime.datetime(2009, 1, 2, 3, 4, 5, 6789)
    """
    if isinstance(value, datetime.datetime):
        return value
    else:
        tokens = re.split(r'-|T|:|\.| ', value)
        return datetime.datetime(*map(int, tokens))
