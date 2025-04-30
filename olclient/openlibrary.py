"""Basic wrapper (client) over OpenLibrary REST API"""


import json
from typing import List, Dict, Optional, Any

import jsonschema
import logging
import os
import re
from urllib.parse import urlencode
from urllib.request import pathname2url

import backoff
import requests
from requests import Response

from olclient import common
from olclient.config import Config
from olclient.entity_helpers.work import get_work_helper_class
from olclient.utils import merge_unique_lists

logger = logging.getLogger('openlibrary')


class OpenLibrary:

    """Open Library API Client.

    Usage:
        >>> from olclient.openlibrary import OpenLibrary
        >>> import olclient.common as common
        >>> ol = OpenLibrary(base_url="http://0.0.0.0:8080")

        ... #  Create a new book
        >>> book = common.Book(title=u"Warlight: A novel", \
        ...     authors=[common.Author(name=u"Michael Ondaatje")], \
        ...     publisher=u"Deckle Edge", publish_date=u"2018")
        >>> book.add_id(u'isbn_10', u'0525521194')
        >>> book.add_id(u'isbn_13', u'9780525521198')
        >>> new_book = ol.create_book(book)
        >>> new_book.add_bookcover('https://images-na.ssl-images-amazon.com/images/I/51kmM%2BvVRJL._SX337_BO1,204,203,200_.jpg')

        ... #  Fetch and update an existing book
        >>> book = ol.get_book_by_isbn(u"3570028364")
        >>> book.title = u"Wie die Weißen Engel die Blauen Tiger zur " \
        ...     "Schnecke machten"
        >>> book.save(comment="correcting title")
    """

    VALID_IDS = ['isbn_10', 'isbn_13', 'lccn', 'ocaid']
    BACKOFF_KWARGS = {
        'wait_gen': backoff.expo,
        'exception': requests.exceptions.RequestException,
        'giveup': lambda e: hasattr(e.response, 'status_code')
        and 400 <= e.response.status_code < 500,
        'max_tries': 5,
    }

    # constants to aid works.json API request's pagination
    WORKS_LIMIT = 50
    WORKS_PAGINATION_OFFSET = 0

    def __init__(self, credentials=None, base_url='https://openlibrary.org'):
        self.session = requests.Session()
        self.base_url = base_url
        credentials = credentials or Config().get_config().get('s3', None)
        if credentials:
            self.login(credentials)

    def login(self, credentials):
        """Login to Open Library with given credentials, ensures the requests
        session has valid cookies for future requests.
        """

        if 'username' in credentials._asdict():
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            data = urlencode(credentials._asdict())
        else:  # s3 login
            headers = {'Content-Type': 'application/json'}
            data = json.dumps(credentials._asdict())
        url = self.base_url + '/account/login'

        err = lambda e: logger.exception("Error at login: %s", e)

        @backoff.on_exception(on_giveup=err, **self.BACKOFF_KWARGS)
        def _login(url, headers, data):
            """Makes best effort to perform request w/ exponential backoff"""
            return self.session.post(url, data=data, headers=headers)

        _ = _login(url, headers, data)

        if not self.session.cookies:
            raise ValueError("No cookie set")

    def validate(self, doc, schema_name):
        """Validates a doc's json representation against
        its JSON Schema using jsonschema.validate().
        Returns:
          None
        Raises:
          jsonschema.exceptions.ValidationError if validation fails.
        """
        path = os.path.dirname(os.path.realpath(__file__))
        schemata_path = os.path.join(path, 'schemata', schema_name)
        with open(schemata_path) as schema_data:
            schema = json.load(schema_data)
            resolver = jsonschema.RefResolver('file:' + pathname2url(schemata_path), schema)
            return jsonschema.Draft4Validator(schema, resolver=resolver).validate(
                doc.json()
            )

    def delete(self, olid, comment):
        """Delete a single Open Library entity by olid (str)
        CAUTION: This does not make any checks for backreference consistency,
        Editions could be orphaned, or books left without Authors. Use with care!
        """
        data = json.dumps({'type': {'key': '/type/delete'}, '_comment': comment})
        url = self._generate_url_from_olid(olid)
        return self.session.put(url, data=data)

    def save_many(self, docs, comment) -> Response:
        """
        Uses the Open Library save_many API endpoint to
        write any number or combination of documents (Edition, Work, or Author)
        back to Open Library.
        Uses HTTP Extension Framework custom headers (RFC 2774).
        """
        headers = {
            'Opt': '"http://openlibrary.org/dev/docs/api"; ns=42',
            '42-comment': comment,
        }
        doc_json = [doc.json() for doc in docs]
        return self.session.post(
            f'{self.base_url}/api/save_many', json.dumps(doc_json), headers=headers
        )

    def delete_many(self, ol_ids: List[str], comment: str) -> Response:
        return self.save_many(
            [self.Delete(ol_id) for ol_id in ol_ids],
            comment=comment
        )

    err = lambda e: logger.exception("Error retrieving OpenLibrary response: %s", e)

    @backoff.on_exception(on_giveup=err, **BACKOFF_KWARGS)  # type: ignore
    def get_ol_response(self, path):
        """Makes best effort to perform request w/ exponential backoff"""
        response = self.session.get(self.base_url + path)
        response.raise_for_status()
        return response

    @property
    def Work(self):
        """
        >>> from olclient import OpenLibrary
        >>> ol = OpenLibrary()
        >>> ol.Work.get(olid)
        """
        return get_work_helper_class(self)

    @property
    def Edition(ol_self):
        class Edition(common.Book):

            OL = ol_self

            def __init__(
                self,
                work_olid,
                edition_olid,
                title,
                subtitle=None,
                identifiers=None,
                number_of_pages=None,
                authors=None,
                publisher=None,
                publish_date=None,
                cover=None,
                **kwargs,
            ):
                """
                Error:
                    TypeError: __init__() missing 2 required positional arguments: 'edition_olid' and 'title'

                Usage:
                    >>> from olclient.openlibrary import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> e = ol.Edition(u'OL2514725W')
                    >>> e.book
                """
                self._work = None
                self.work_olid = work_olid
                self.olid = edition_olid
                self.description = OpenLibrary.get_text_value(
                    kwargs.pop('description', None)
                )
                self.notes = OpenLibrary.get_text_value(kwargs.pop('notes', None))
                super().__init__(
                    title,
                    subtitle=subtitle,
                    identifiers=identifiers,
                    number_of_pages=number_of_pages,
                    authors=authors,
                    publisher=publisher,
                    publish_date=publish_date,
                    cover=cover,
                    **kwargs,
                )

            @staticmethod
            def _validate_identifiers(identifiers):
                """Don't reject existing identifiers from Open Library."""
                return

            @property
            def work(self):
                self._work = self.OL.Work.get(self.work_olid)
                return self._work

            def json(self):
                """Returns a dict JSON representation of an OL Edition suitable
                for saving back to Open Library via its APIs.
                """
                exclude = ['_work', 'olid', 'work_olid', 'pages']
                data = {
                    k: v for k, v in self.__dict__.items() if v and k not in exclude
                }
                data['key'] = '/books/' + self.olid
                data['type'] = {'key': '/type/edition'}
                if self.pages:
                    data['number_of_pages'] = self.pages
                if self.work_olid:
                    data['works'] = [{'key': '/works/' + self.work_olid}]
                if self.authors:
                    data['authors'] = [
                        {'key': '/authors/' + a.olid} for a in self.authors
                    ]
                if data.get('description'):
                    data['description'] = {
                        'type': '/type/text',
                        'value': data['description'],
                    }
                if data.get('notes'):
                    data['notes'] = {'type': '/type/text', 'value': data['notes']}
                return data

            def validate(self):
                """Validates an Edition's json representation against the canonical
                JSON Schema for Editions using jsonschema.validate().
                Returns:
                   None
                Raises:
                   jsonschema.exceptions.ValidationError if the Edition is invalid.
                """
                return self.OL.validate(self, 'edition.schema.json')

            def add_bookcover(self, cover_url):
                """Adds a cover image to this edition"""
                url = f'{self.OL.base_url}/books/{self.olid}/-/add-cover'
                r = self.OL.session.post(
                    url, files={'file': '', 'url': cover_url, 'upload': 'submit'}
                )
                return r

            def add_book_cover_from_file(
                    self,
                    file_name: str,
                    cover_data: bytes,
                    mime_type: str = "image/jpeg",
            ):
                form_data_body = {
                    "file": (file_name, cover_data, mime_type),
                    "url": (None, "https://"),
                    "upload": (None, "Submit")
                }
                return self.OL.session.post(
                    f'{self.OL.base_url}/books/{self.olid}/-/add-cover',
                    files=form_data_body
                )

            def save(self, comment):
                """Saves this edition back to Open Library using the JSON API."""
                body = self.json()
                body['_comment'] = comment
                url = self.OL.base_url + f'/books/{self.olid}.json'
                return self.OL.session.put(url, json.dumps(body))

            @classmethod
            def create(cls, book, work_olid, debug=False):
                """Creates this book as an Edition associated with the work having
                olid work_olid

                Args:
                    book (common.Book)
                    work_olid (unicode) - The olid of the work to add this book to

                Returns:
                    Edition Object

                Usage:
                    >>> from olclient import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> = ol.Edition.create(Book(...), u'OL2514725W')
                """
                return cls.OL.create_book(book, work_olid=work_olid, debug=debug)

            @classmethod
            def ol_edition_json_to_book_args(cls, data):
                """Creates Book Arguments from OL Edition JSON

                Args:
                    json - {"edition_olid":"XXX", "authors":["XXX","XXX"], "work_olid":"XXX"}

                Returns:
                    book arguments Dictionary

                Usage:
                    >>> from olclient import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> = ol.Edition.ol_edition_json_to_book_args(data)
                """
                book_args = {
                    'edition_olid': data.pop('key', '').split('/')[-1],
                    'work_olid': data.pop('works')[0]['key'].split('/')[-1]
                    if 'works' in data
                    else None,
                    'authors': [
                        cls.OL.Author.get(author['key'].split('/')[-1])
                        for author in data.pop('authors', [])
                    ],
                }
                book_args.update(data)
                return book_args

            @classmethod
            def get(cls, olid=None, isbn=None, oclc=None, lccn=None, ocaid=None):
                """Retrieves a single book from OpenLibrary as json by isbn or olid or ocaid or lccn or oclc or olid.

                Args:
                    identifier (unicode) - identifier value, e.g. u'OL20933604M'

                Warnings:
                    Currently, the marshaling is not complete. While it generates/returns a valid book, ideally we want
                    the OpenLibrary fields to be converted into a format which is consistent with how we are using
                    olclient Book to create OpenLibrary books -- i.e. authors = Author objects, publishers list
                    instead of publisher, identifiers (instead of key and isbn). The goal is to enable service to
                    interoperate with the Book object and for OpenLibrary to be able to marshal the book object
                    into a form it can use (or marshal its internal book json into a form others can use).

                Usage:
                    >>> from olclient import OpenLibrary
                    >>> ol = OpenLibrary()

                    >>> ol.Edition.get(olid=u'OL25944230M')
                    or
                    >>> ol.Edition.get(isbn=u'9706664998')
                    or
                    >>> ol.Edition.get(oclc=u'893562252')
                    or
                    >>> ol.Edition.get(lccn=u'XXX')
                    or
                    >>> ol.Edition.get(ocaid=u'XXX')
                """
                if not any([olid, isbn, oclc, lccn, ocaid]):
                    raise ValueError(
                        "Must supply valid olid, isbn, oclc, ocaid, or lccn"
                    )
                elif not olid:
                    bibkeys = {'ISBN': isbn, 'OCLC': oclc, 'OCAID': ocaid, 'LCCN': lccn}
                    bibkey, value = [(k, v) for k, v in bibkeys.items() if v][0]
                    olid = cls.get_olid(bibkey, value)
                    if not olid:
                        # No edition found by bibkey
                        return

                path = f'/books/{olid}.json'
                response = cls.OL.get_ol_response(path)

                try:
                    data = response.json()
                    data['title'] = data.get('title', None)
                    edition = cls(**cls.ol_edition_json_to_book_args(data))
                    return edition
                except Exception as e:
                    raise Exception(
                        f"Unable to get Edition with olid: {olid}\nDetails: {e}"
                    )

            @classmethod
            def get_olid_by_ocaid(cls, ocaid):
                return cls.get_olid('OCAID', ocaid)

            @classmethod
            def get_olid_by_isbn(cls, isbn):
                return cls.get_olid('ISBN', isbn)

            @classmethod
            def get_olid_by_lccn(cls, lccn):
                return cls.get_olid('LCCN', lccn)

            @classmethod
            def get_olid_by_oclc(cls, oclc):
                return cls.get_olid('OCLC', oclc)

            @classmethod
            def get_olid(cls, key, value):
                """Looks up a key (LCCN, OCLC, ISBN10/13, OCAID) in OpenLibrary and returns a
                matching olid if a match exists.

                Args:
                    key (unicode) - u'OCLC', u'ISBN', u'LCCN', u'OCAID'
                    value (unicode) - identifier value

                Returns:
                    olid (unicode) or None
                """
                metadata = cls.get_metadata(key, value)
                if metadata:
                    book_url = metadata.get('info_url', '')
                    return cls.OL._extract_olid_from_url(book_url, url_type="books")

            @classmethod
            def get_metadata(cls, key, value):
                """Looks up a key (LCCN, OCLC, ISBN10/13, OCAID) using the Open Library
                Books API https://openlibrary.org/dev/docs/api/books
                Returns first matched JSON object for the bibliographic key,
                or None if there is no match.

                Response keys:
                    'bib_key': Identifier used to query this book.
                    'info_url': A URL to the book page.
                    'preview': Preview state, 'noview' or 'full'.
                    'preview_url': A URL to the preview of the book.
                    'thumbnail_url': A URL to a bookcover thumbnail.

                Args:
                    key (unicode) - u'OCLC', u'ISBN', u'LCCN', u'OCAID'
                    value (unicode) - identifier value

                Returns:
                    Dict or None

                Usage:
                    >>> from olclient import OpenLibrary
                    >>> ol = OpenLibrary()

                    >>> ol.Edition.get_metadata(u'ISBN', u'9780747550303')
                    or
                    >>> ol.Edition.get_metadata(u'OCLC', u'XXX')
                    or
                    >>> ol.Edition.get_metadata(u'LCCN', u'XXX')
                    or
                    >>> ol.Edition.get_metadata(u'OCAID', u'XXX')
                """
                if key not in ['OCLC', 'ISBN', 'LCCN', 'OLID', 'OCAID']:
                    raise ValueError(
                        "key must be one of OCLC, OLID, ISBN, OCAID, or LCCN"
                    )

                path = f'/api/books.json?bibkeys={key}:{value}'
                response = cls.OL.get_ol_response(path)

                try:
                    results = response.json()
                except ValueError as e:
                    logger.exception(e)
                    return None
                _key = f'{key}:{value}'
                if _key in results:
                    return results[_key]
                return None

        return Edition

    @property
    def Author(ol_self):
        class Author(common.Author):

            OL = ol_self

            def __init__(self, olid, name, **author_kwargs):
                self.olid = olid
                super().__init__(name, **author_kwargs)

            @staticmethod
            def _validate_name(name):
                """Don't reject existing author names from Open Library."""
                return

            def json(self):
                """Returns a dict JSON representation of an OL Author suitable
                for saving back to Open Library via its APIs.
                """
                exclude = ['olid', 'identifiers']
                data = {
                    k: v for k, v in self.__dict__.items() if v and k not in exclude
                }
                data['key'] = '/authors/' + self.olid
                data['type'] = {'key': '/type/author'}
                if 'bio' in data:
                    data['bio'] = {'type': '/type/text', 'value': data['bio']}
                return data

            def validate(self):
                """Validates an Author's json representation against the canonical
                JSON Schema for Authors using jsonschema.validate().
                Returns:
                   None
                Raises:
                   jsonschema.exceptions.ValidationError if the Author is invalid.
                """
                return self.OL.validate(self, 'author.schema.json')

            def save(self, comment):
                """Saves this author back to Open Library using the JSON API."""
                body = self.json()
                body['_comment'] = comment
                url = self.OL.base_url + f'/authors/{self.olid}.json'
                return self.OL.session.put(url, json.dumps(body))

            def works(self, limit=OL.WORKS_LIMIT, offset=OL.WORKS_PAGINATION_OFFSET):
                """Returns a list of OpenLibrary Works associated with an OpenLibrary Author.

                Args:
                    olid (unicode) - OpenLibrary ID for author to search within
                                    Open Library's database of authors to retrieve his Works.
                    name (unicode) - name of an Author to search for within OpenLibrary.
                    limit (integer) - number of Author's Works to return.
                    offset (integer) - offset number to aid pagination.
                Returns:
                    A (list) of Works from the OpenLibrary associated with the
                    Author.

                Usage:
                    >>> from olclient.openlibrary import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> ol.Author.get('OL39307A').works()
                    or
                    >>> ol.Author.get('OL39307A').works(limit=20)# to obtain the first 20 works of the author
                    >>> ol.Author.get('OL39307A').works(limit=20, offset=20)# to obtain the next 20 works of the author
                    or
                    >>> author_obj = ol.Author.get(ol.Author.get_olid_by_name('Dan Brown'))
                    >>> author_obj.works()
                    or
                    >>> ol.Author.get(ol.Author.get_olid_by_name('Dan Brown')).works()
                """
                path = f'/authors/{self.olid}/works.json'

                # check to prevent 'None' value
                limit = limit or self.OL.WORKS_LIMIT
                offset = offset or self.OL.WORKS_PAGINATION_OFFSET

                # including limit and offset querystrings to the url
                path += f'/?limit={limit}&offset={offset}'

                try:
                    response = self.OL.get_ol_response(path)
                    return response.json()
                except Exception as e:
                    logger.exception(e)
                    raise Exception("Author API failed to return json")

            @classmethod
            def get(cls, olid):
                """Retrieves an OpenLibrary Author by author_olid
                Args:
                    olid (unicode) - OpenLibrary ID for author to search within
                                    Open Library's database of authors

                Returns:
                    A (list) of author object from the OpenLibrary
                    authors autocomplete API

                Usage:
                    >>> from olclient.openlibrary import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> ol.Author.get('OL39307A')
                """
                path = f'/authors/{olid}.json'
                r = cls.OL.get_ol_response(path)
                try:
                    data = r.json()
                    olid = cls.OL._extract_olid_from_url(
                        data.pop('key', ''), url_type='authors'
                    )
                except:
                    raise Exception(f"Unable to get Author with olid: {olid}")

                return cls(
                    olid,
                    name=data.pop('name', ''),
                    bio=OpenLibrary.get_text_value(data.pop('bio', None)),
                    **data,
                )

            @classmethod
            def search(cls, name, limit=1):
                """Finds a list of OpenLibrary authors with similar names to the
                search query using the Author auto-complete API.

                Args:
                    name (unicode) - name of author to search for within OpenLibrary's
                                     database of authors
                    limit (integer) - number of objects with similar names

                Returns:
                    A (list) of matching authors from the OpenLibrary
                    authors autocomplete API

                Usage:
                    >>> from olclient.openlibrary import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> ol.Author.search('Dan Brown')
                    or
                    >>> ol.Author.search('Dan Brown', 5)
                """
                if name:
                    err = lambda e: logger.exception(
                        "Error fetching author matches: %s", e
                    )
                    url = cls.OL.base_url + '/authors/_autocomplete?q={}&limit={}'.format(
                        name,
                        limit,
                    )

                    @backoff.on_exception(on_giveup=err, **cls.OL.BACKOFF_KWARGS)
                    def _get_matching_authors_by_name(url):
                        """Makes best effort to perform request w/ exponential backoff"""
                        return cls.OL.session.get(url)

                    response = _get_matching_authors_by_name(url)
                    author_matches = response.json()
                    return author_matches
                return []

            @classmethod
            def get_olid_by_name(cls, name):
                """Uses the Authors auto-complete API to find OpenLibrary Authors with
                similar names. If any name is an exact match then return the
                matching author's 'key' (i.e. olid). Otherwise, return None.

                FIXME Warning: if there are multiple exact matches, (e.g. a common
                name like "Mike Smith" which may have multiple valid results), this
                presents a problem.

                Args:
                    name (unicode) - name of an Author to search for within OpenLibrary

                Returns:
                    olid (unicode)

                Usage:
                    >>> from olclient.openlibrary import OpenLibrary
                    >>> ol = OpenLibrary()
                    >>> ol.Author.get_olid_by_name('Dan Brown')
                """
                authors = cls.search(name)
                _name = name.lower().strip()
                for author in authors:
                    if _name == author['name'].lower().strip():
                        return author['key'].split('/')[-1]
                return None

        # This returns the Author class from the ol.Author factory method
        return Author

    @property
    def Delete(ol_self):
        class Delete(common.Entity):
            OL = ol_self

            def __init__(self, doc):
                """Creates a delete object from the either the <Author | Edition | Work>
                OR an olid.
                """
                try:
                    self.olid = doc.olid
                except AttributeError:
                    self.olid = doc

            def json(self):
                data = {
                    'key': OpenLibrary.full_key(self.olid),
                    'type': {'key': '/type/delete'},
                }
                return data

            def save(self, comment='delete'):
                """Saves the Delete back to Open Library using the JSON API."""
                body = self.json()
                body['_comment'] = comment
                url = self.OL._generate_url_from_olid(self.olid)
                return self.OL.session.put(url, json.dumps(body))

        return Delete

    @property
    def Redirect(ol_self):
        class Redirect(common.Entity):
            OL = ol_self

            def __init__(self, **kwargs):
                """
                Usage:
                    >>> r = ol.Redirect(f=u'OL2514725W', t=u'OL1234W')
                  OR
                    >>> r = ol.Redirect(f=<ol.Edition>, t=<ol.Edition>)
                """
                try:
                    self.olid = kwargs['f'].olid
                except AttributeError:
                    self.olid = kwargs['f']

                try:
                    self.location = kwargs['t'].olid
                except AttributeError:
                    self.location = kwargs['t']

                self.olid = self.olid.upper()
                self.location = self.location.upper()

                if OpenLibrary.get_type(self.olid) != OpenLibrary.get_type(
                    self.location
                ):
                    raise Exception("Types don't match!")

            def json(self):
                data = {
                    'key': OpenLibrary.full_key(self.olid),
                    'location': OpenLibrary.full_key(self.location),
                    'type': {'key': '/type/redirect'},
                }
                return data

            def save(self, comment='redirect'):
                """Saves the Redirect back to Open Library using the JSON API."""
                body = self.json()
                body['_comment'] = comment
                url = self.OL._generate_url_from_olid(self.olid)
                return self.OL.session.put(url, json.dumps(body))

        return Redirect

    def get(self, olid):
        _olid = olid.lower()
        if _olid.endswith('m'):
            return self.Edition.get(olid)
        elif _olid.endswith('w'):
            return self.Work.get(olid)
        elif _olid.endswith('a'):
            return self.Author.get(olid)

    @classmethod
    def get_primary_identifier(cls, book):
        """XXX needs docs"""
        id_name, id_value = None, None
        for valid_key in cls.VALID_IDS:
            if valid_key in book.identifiers:
                id_name = valid_key
                id_value = book.identifiers[valid_key][0]
                break

        if not (id_name and id_value):
            raise ValueError("ISBN10/13 or LCCN required")
        return id_name, id_value

    def create_book(self, book, work_olid=None, debug=False):
        """Create a new OpenLibrary Book using the /books/add endpoint

        Args:
           book (Book)
           work_olid (unicode) - if present, associates this edition
                                 with an existing work.
           debug (bool) - whether to create the book or return it as data

        Usage:
            >>> ol = OpenLibrary()
            ... book = ol.create_book(Book(
            ...     title=u"Wie die Weißen Engel die Blauen Tiger zur " \
            ...         "Schnecke machten",
            ...     author=Author(name=u"Walter Kort"),
            ...     publisher=u"Bertelsmann",
            ...     isbn=u"3570028364", publish_date=u"1982"))
        """
        id_name, id_value = self.get_primary_identifier(book)


        if len(book.authors) == 0 :
            raise ValueError("Unable to create_book without valid Author name")
        author_keys = {}
        for _author in book.authors:
            author_olid = self.Author.get_olid_by_name(_author.name)
            author_keys[_author.name] = ('/authors/' + author_olid) if author_olid else '__new__'
        return self._create_book(
            title=book.title,
            author_names=author_keys.keys(),
            author_keys=author_keys,
            publish_date=book.publish_date,
            publisher=book.publisher,
            id_name=id_name,
            id_value=id_value,
            work_olid=work_olid,
            debug=debug,
        )

    def _create_book(
        self,
        title,
        author_names,
        author_keys,
        publish_date,
        publisher,
        id_name,
        id_value,
        work_olid=None,
        debug=False,
    ):
        """
        Returns:
            An (OpenLibrary.Edition)
        """
        if id_name not in self.VALID_IDS:
            raise ValueError(
                f"Invalid `id_name`. Must be one of {self.VALID_IDS}, got {id_name}"
            )

        err = lambda e: logger.exception("Error creating OpenLibrary " "book: %s", e)
        url = self.base_url + '/books/add'
        if work_olid:
            url += f'?work=/works/{work_olid}'
        data = {
            "book_title": title,
            "publish_date": publish_date,
            "publisher": publisher,
            "id_name": id_name,
            "id_value": id_value,
            "_save": "",
        }
        for i,_name in enumerate(author_names):
            data[f"author_names--{i}"] = _name
            data[f"authors--{i}--author--key"] = author_keys[_name]

        if debug:
            return data

        @backoff.on_exception(on_giveup=err, **self.BACKOFF_KWARGS)
        def _create_book_post(url, data=data):
            """Makes best effort to perform request w/ exponential backoff"""
            return self.session.post(url, data=data)

        response = _create_book_post(url, data=data)
        _olid = self._extract_olid_from_url(response.url, url_type="books")
        if _olid == 'add':
            raise ValueError('Creation failed, book may already exist!')
        return self.Edition.get(_olid)

    def _generate_url_from_olid(self, olid):
        """Returns the .json url for an olid (str)"""
        ol_paths = {'OL..A': 'authors', 'OL..M': 'books', 'OL..W': 'works'}
        kind = re.sub(r'\d+', '..', olid)
        return f"{self.base_url}/{ol_paths[kind]}/{olid}.json"

    @staticmethod
    def get_text_value(text):
        """Returns the text value from a property that can either be a properly
        formed /type/text object, or a (incorrect) string.
        Used for Work/Edition 'notes' and 'description' and Author 'bio'.
        """
        try:
            return text.get('value')
        except:
            return text

    @staticmethod
    def get_type(olid):
        ol_types = {'OL..A': 'author', 'OL..M': 'book', 'OL..W': 'work'}
        kind = re.sub(r'\d+', '..', olid)
        try:
            return ol_types[kind]
        except KeyError:
            raise ValueError(f"Unknown type for olid: {olid}")

    @staticmethod
    def full_key(olid):
        """Returns the Open Library JSON key of format /<type(plural)>/<olid> as used by the
        Open Library API."""
        return f"/{OpenLibrary.get_type(olid)}s/{olid}"

    @staticmethod
    def _extract_olid_from_url(url, url_type):
        """No single field has the match's OpenLibrary ID in isolation so we
        extract it from the info_url field.

        Args:
            url_type (unicode) - "books", "authors", "works", etc
                                 which are found in the ol url, e.g.:
                                 openlibrary.org/books/...

        Returns:
            olid (unicode)

        Usage:
            >>> url = u'https://openlibrary.org/books/OL25943366M'
            >>> _extract_olid_from_url(url, u"books")
                u"OL25943366M"
        """
        ol_url_pattern = r'[/]%s[/]([0-9a-zA-Z]+)' % url_type
        try:
            return re.search(ol_url_pattern, url).group(1)
        except AttributeError:
            return None  # No match
