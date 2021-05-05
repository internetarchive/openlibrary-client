#!/usr/bin/env python

"""
    cli.py
    ~~~~~~

    The `ol` command line utility

    :copyright: (c) 2016 by Internet Archive.
    :license: see LICENSE for more details.
"""

import argparse
import getpass
import json
import jsonpickle
import sys

import internetarchive as ia

from . import __title__, __version__, OpenLibrary, common
from .config import Config, Credentials


def argparser():
    """Parses command line options and returns an args object"""
    parser = argparse.ArgumentParser(description=__title__)
    parser.add_argument(
        '-v',
        help="Displays the currently installed " "version of ol",
        action="version",
        version=f"{__title__} v{__version__}",
    )
    parser.add_argument(
        '--configure', action='store_true', help='Configure ol client with credentials'
    )
    parser.add_argument(
        '--get-work', action='store_true', help='Get a work by --title, --olid'
    )
    parser.add_argument(
        '--get-author-works',
        action='store_true',
        help='Get a works of an author providing author\'s --olid, --author-name ',
    )
    parser.add_argument(
        '--get-book', action='store_true', help='Get a book by --isbn, --olid'
    )
    parser.add_argument(
        '--get-olid', action='store_true', help='Get an olid by --title or --isbn'
    )
    parser.add_argument('--olid', default=None, help="Specify an olid as an argument")
    parser.add_argument('--isbn', default=None, help="Specify an isbn as an argument")
    parser.add_argument('--create', default='', help='Create a new work from json')
    parser.add_argument('--title', default=None, help="Specify a title as an argument")
    parser.add_argument(
        '--author-name', default=None, help="Specify an author as an argument"
    )
    parser.add_argument(
        '--baseurl', default='https://openlibrary.org', help="Which OL backend to use"
    )
    parser.add_argument(
        '--email',
        default=None,
        help="An IA email for requests which "
        "require authentication. You will be prompted "
        "discretely for a password",
    )

    # --create : to create a book (e.g. --title, --author, --isbn, ...)
    # --edit : to edit an OL book (e.g. --olid OLXXXXX, ...)
    return parser


def main() -> None:
    parser = argparser()
    args = parser.parse_args()

    if args.configure:
        email = args.email or input("Archive.org Email: ")
        if not email:
            raise ValueError("--email required for configuration")
        password = getpass.getpass("Password: ")

        ia.configure(email, password)
        config_tool = Config()
        config = config_tool._get_config()
        config['s3'] = ia.config.get_config()['s3']

        try:
            ol = OpenLibrary(
                credentials=Credentials(**config['s3']), base_url=args.baseurl
            )
        except:
            sys.stderr.write("Incorrect credentials, not updating config.")
            return

        config_tool.update(config)
        print("Successfully configured")
        return

    # prompt first time users to configure their OpenLibrary credentials
    try:
        ol = OpenLibrary()
    except ValueError as e:
        if str(e) == 'No cookie set':
            print(
                "Seems like you haven't configured your olclient with credentials.\n"
                "You can configure olclient using the following command:\n"
                "$ol --configure --email <EMAIL>\n"
            )
            return parser.print_help()
        else:
            raise

    if args.get_olid:
        print(ol.Edition.get_olid_by_isbn(args.isbn))
    elif args.get_book:
        if args.olid:
            print(jsonpickle.encode(ol.Edition.get(olid=args.olid)))
        elif args.isbn:
            print(jsonpickle.encode(ol.Edition.get(isbn=args.isbn)))
    elif args.get_work:
        if args.olid:
            print(jsonpickle.encode(ol.Work.get(args.olid)))
        elif args.title:
            print(jsonpickle.encode(ol.Work.search(args.title)))
    elif args.get_author_works:
        if args.olid:
            print(jsonpickle.encode(ol.Author.get(args.olid).works()))
        elif args.author_name:
            print(
                jsonpickle.encode(
                    ol.Author.get(ol.Author.get_olid_by_name(args.author_name)).works()
                )
            )
    elif args.create:
        data = json.loads(args.create)
        title = data.pop('title')
        author = common.Author(data.pop('author'))
        book = common.Book(title, authors=[author], **data)
        edition = ol.Work.create(book)
        print(edition.olid)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
