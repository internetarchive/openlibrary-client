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
import sys

from . import __title__, __version__, OpenLibrary, MARC


def argparser():
    """Parses command line options and returns an args object"""
    parser = argparse.ArgumentParser(description=__title__)
    parser.add_argument('-v', help="Displays the currently installed " \
                        "version of ol", action="version",
                        version="%s v%s" % (__title__, __version__))
    parser.add_argument('--get-work', action='store_true',
                        help='Get a work by --title, --olid')
    parser.add_argument('--get-book', action='store_true',
                        help='Get a book by --isbn, --olid')
    parser.add_argument('--get-olid', action='store_true',
                        help='Get an olid by --title or --isbn')
    parser.add_argument('--olid', default=None,
                        help="Specify an olid as an argument")
    parser.add_argument('--isbn', default=None,
                        help="Specify an isbn as an argument")
    parser.add_argument('--title', default=None,
                        help="Specify a title as an argument")
    
    # --marc : to convert marcs (e.g. --file <path> --from <line> --to <bin)>
    # --create : to create a book (e.g. --title, --author, --isbn, ...)
    # --edit : to edit an OL book (e.g. --olid OLXXXXX, ...)
    return parser


def main():
    ol = OpenLibrary()
    parser = argparser()
    args = parser.parse_args()
    if args.get_olid:
        print(ol.Edition.get_olid_by_isbn(args.isbn))
    elif args.get_book:
        if args.olid:
            print(ol.Edition.get(olid=args.olid))
        elif args.isbn:
            print(ol.Edition.get(isbn=args.isbn))
    elif args.get_work:
        if args.olid:
            print(ol.Work.get(args.olid))
        elif args.title:
            print(ol.Work.search(args.title))
    else:
        print(parser.print_help())


if __name__ == "__main__":
    main()
