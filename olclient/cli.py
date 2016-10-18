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
import jsonpickle
import sys

from . import __title__, __version__, OpenLibrary, MARC
from .config import Config, Credentials

def argparser():
    """Parses command line options and returns an args object"""
    parser = argparse.ArgumentParser(description=__title__)
    parser.add_argument('-v', help="Displays the currently installed " \
                        "version of ol", action="version",
                        version="%s v%s" % (__title__, __version__))
    parser.add_argument('--configure', action='store_true',
                        help='Configure ol client with credentials')
    parser.add_argument('--get-work', action='store_true',
                        help='Get a work by --title, --olid')
    parser.add_argument('--get-book', action='store_true',
                        help='Get a book by --isbn, --olid')
    parser.add_argument('--get-olid', action='store_true',
                        help='Get an olid by --title or --isbn')
    parser.add_argument('--olid', default=None,
                        help="Specify an olid as an argument")
    parser.add_argument('--isbn', type=lambda s: unicode(s, 'utf8'),
                        default=None,
                        help="Specify an isbn as an argument")
    parser.add_argument('--title', default=None,
                        help="Specify a title as an argument")
    parser.add_argument('--username', default=None,
                        help="An OL username for requests which " \
                        "require authentication. You will be prompted " \
                        "discretely for a password")
    
    # --marc : to convert marcs (e.g. --file <path> --from <line> --to <bin)>
    # --create : to create a book (e.g. --title, --author, --isbn, ...)
    # --edit : to edit an OL book (e.g. --olid OLXXXXX, ...)
    return parser


def main():
    parser = argparser()
    args = parser.parse_args()

    if args.configure:
        username = args.username
        if not username:
            raise ValueError("--username required for configuration")
        password = getpass.getpass("Password: ")
        config_tool = Config()
        config = config_tool._get_config()
        config['openlibrary'] = {
            u'username': username,
            u'password': password
        }
        try:
            ol = OpenLibrary(credentials=Credentials(username, password))
        except:
            return "Incorrect credentials, not updating config."

        config_tool.update(config)
        return "Successfully configured "

    ol = OpenLibrary()
    if args.get_olid:
        return ol.Edition.get_olid_by_isbn(args.isbn)
    elif args.get_book:
        if args.olid:
            return jsonpickle.encode(ol.Edition.get(olid=args.olid))
        elif args.isbn:
            return jsonpickle.encode(ol.Edition.get(isbn=args.isbn))
    elif args.get_work:
        if args.olid:
            return jsonpickle.encode(ol.Work.get(args.olid))
        elif args.title:
            return jsonpickle.encode(ol.Work.search(args.title))
    else:
        return parser.print_help()


if __name__ == "__main__":
    main()
