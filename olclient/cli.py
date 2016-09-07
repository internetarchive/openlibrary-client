#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    cli.py
    ~~~~~~

    The `ol` command line utility

    :copyright: (c) 2016 by Internet Archive.
    :license: see LICENSE for more details.
"""

from __future__ import absolute_import, division, print_function

import argparse
import getpass
from . import __title__, __version__, OpenLibrary, MARC


def argparser():
    """Parses command line options and returns an args object"""
    parser = argparse.ArgumentParser(description=__title__)
    parser.add_argument('-v', help="Displays the currently installed " \
                        "version of ol", action="version",
                        version="%s v%s" % (__title__, __version__))
    # --marc : to convert marcs (e.g. --file <path> --from <line> --to <bin)>
    # --create : to create a book (e.g. --title, --author, --isbn, ...)
    # --edit : to edit an OL book (e.g. --olid OLXXXXX, ...)
    return parser.parse_args()


def main():
    args = argparser()


if __name__ == "__main__":
    main()
