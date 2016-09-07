#-*- encoding: utf-8 -*-

"""Basic wrapper (client) over OpenLibrary REST API"""

from __future__ import absolute_import, division, print_function

from collections import namedtuple
import datetime
import logging
import json
import re
import requests
import urllib, urllib2

from .book import Book, Author
from .config import Config
from .utils import parse_datetime


logger = logging.getLogger('openlibrary')


class OpenLibrary(object):

    """Open Library API Client.

    Usage:
        >>> ol = OpenLibrary("http://0.0.0.0:8080")
        ... #  Create a new book
        ... book = ol.create_book(Book(
        ...     title=u"Wie die Weißen Engel die Blauen Tiger zur Schnecke machten",
        ...     author=Author(name=u"Walter Kort"), publisher=u"Bertelsmann",
        ...     isbn=u"3570028364", publish_date=u"1982"))

        >>> ol = OpenLibrary("http://0.0.0.0:8080")
        ... #  Fetch and update an existing book
        ... book = ol.get_book_by_isbn(u"3570028364")
        ... book.title = u"Wie die Weißen Engel die Blauen Tiger zur Schnecke machten"
        ... book.save(comment="correcting title")
    """

    def __init__(self, base_url=None, credentials=None):
        ol_config = Config().get_config()['openlibrary']
        self.base_url = (base_url or ol_config['url']).rstrip('/')
        self.session = requests.Session()
        credentials = credentials or ol_config.get('credentials')
        if credentials:
            self.username = credentials.username
            self.login(credentials)

    def login(self, credentials):
        """Login to Open Library with given credentials"""
        headers = {'Content-Type': 'application/json'}
        url = self.base_url + '/account/login'
        data = json.dumps(credentials._asdict())
        try:
            response = self.session.post(url, data=data, headers=headers)
        except requests.exceptions.RequestException as e:
            logger.exception("Error at login: %s", e)
            raise Exception("Error at login: %s", e)

        if 'Set-Cookie' not in response.headers:
            raise Exception("No cookie set")

    def get_matching_authors_by_name(self, name, limit=1):
        """Finds a list of OpenLibrary authors with similar names to the
        search query using the Author auto-complete API.

        Args:
            name (unicode) - name of author to search for within OpenLibrary's
                             database of authors

        Returns:
            A (list) of matching authors from the OpenLibrary
            authors autocomplete API
        """
        if name:
            url = self.base_url + '/authors/_autocomplete?q=%s&limit=%s' \
                  % (name, limit)
            try:
                response = self.session.get(url)
            except requests.exceptions.RequestException as e:
                logger.exception("Error fetching author matches: %s", e)
                return None

            author_matches = response.json()
            return author_matches
        return []

    def get_matching_authors_olid(self, name):
        """Uses the Authors auto-complete API to find OpenLibrary Authors with
        similar names. If any name is an exact match and there's only
        one exact match (e.g. not a common name like "Mike Smith"
        which may have multiple valid results) then return the
        matching author's 'key' (i.e. olid). Otherwise, return None

        Args:
            name (unicode) - name of an Author to search for within OpenLibrary

        Returns:
            olid (unicode)  -
        """
        authors = self.get_matching_authors_by_name(name)
        _name = name.lower().strip()
        for author in authors:
            if _name == author['name'].lower().strip():
                return author['key'].split('/')[-1]
        return None

    def create_book(self, book, debug=False):
        """Create a new OpenLibrary Book using the /books/add endpoint

        Args:
           book (Book)

        Usage:
            >>> ol = OpenLibrary()
            ... book = ol.create_book(Book(
            ...     title=u"Wie die Weißen Engel die Blauen Tiger zur Schnecke machten",
            ...     author=Author(name=u"Walter Kort"), publisher=u"Bertelsmann",
            ...     isbn=u"3570028364", publish_date=u"1982"))
        """
        def get_primary_identifier():
            id_name, id_value = None, None
            for valid_key in ['isbn_10', 'isbn_13', 'lccn']:
                if valid_key in book.identifiers:
                    id_name = valid_key
                    id_value = book.identifiers[valid_key][0]

            if not (id_name and id_value):
                raise ValueError("ISBN10/13 or LCCN required")
            return id_name, id_value

        id_name, id_value = get_primary_identifier()
        primary_author = book.primary_author
        author_name = primary_author.name if primary_author else u""
        author_olid = self.get_matching_authors_olid(author_name)
        author_key = ('/authors/' + author_olid) if author_olid else  u'__new__'
        data = {
            "title": book.title,
            "author_name": author_name,
            "author_key": author_key,
            "publish_date": book.publish_date,
            "publisher": book.publisher,
            "id_name": id_name,
            "id_value": id_value,
            "_save": ""
        }

        if debug:
            return data

        url = self.base_url + '/books/add'
        try:
            response = self.session.post(url, data=data)
            return self._extract_olid_from_url(response.url, url_type="books")
        except requests.exceptions.RequestException as e:
            logger.exception("Error creating OpenLibrary book: %s", e)

    def get_book_by_olid(self, olid):
        url = self.base_url + '/books/%s.json' % olid
        print(url)
        try:
            response = self.session.get(url)
        except requests.exceptions.RequestException as e:
            logger.exception("Error retrieving OpenLibrary book: %s", e)            
            return None
        # XXX need a way to convert OL book json -> book (and back)
        return Book(**response.json())

    def get_book_by_metadata(self, title, author=None):
        """Get the *closest* matching result in OpenLibrary based on a title
        and author.

        Args:
            title (unicode)
            author (unicode)

        Returns:
            (book.Book)

        Usage:
            >>> ol = OpenLibrary()
            ... ol.get_book_by_metadata(title=u'The Autobiography of Benjamin Franklin')
        """
        url = '%s/search.json?title=%s' % (self.base_url, title)
        if author:
            url += '&author=%s' % author
        resp = requests.get(url)

        try:
            results = Results(**resp.json())
        except ValueError as e:
            logger.exception(e)
            return None

        if results.num_found:
            return results.first.to_book()

        return None

    def get_book_by_isbn(self, isbn):
        """Marshals the output OpenLibrary Book json API
        into (Book) format

        Args:
            isbn (unicode)

        Returns:
            (Book) from the books API endpoint for an item if it
            exists (see fields at
            https://openlibrary.org/dev/docs/api/books) or None if
            there is no match or if the json is malformed.

        Usage:
        """
        url = self.base_url + '/api/books?bibkeys=ISBN:' + isbn + '&format=json&jscmd=data'
        resp = requests.get(url)
        isbn_key = u'ISBN:%s' % isbn
        try:
            result = resp.json()
        except ValueError as e:
            logger.exception(e)
            return None

        if isbn_key in result:
            edition = result[isbn_key]
            edition['identifiers'][u'olid'] = [edition.pop('key').rsplit('/', 1)[1]]
            authors = edition.pop('authors', [])
            edition['authors'] = [
                Author(name=author['name'], olid=self._extract_olid_from_url(
                    author['url'], url_type="authors"))
                for author in authors]
            return Book(**edition)

        return None

    def get_olid_by_isbn(self, isbn):
        """Looks up a ISBN10/13 in OpenLibrary and returns a matching olid (by
        default) or metadata (if metadata=True specified) if a match exists.

        Args:
            isbn (unicode)

        Returns:
            olid (unicode) or None

        Usage:
            >>> ol = OpenLibrary()
            ... ol.get_book_by_isbn(u'9780747550303')
            u'OL1429049M'
        """
        url = self.base_url + '/api/books?bibkeys=ISBN:' + isbn + '&format=json'
        resp = requests.get(url)
        try:
            results = resp.json()
        except ValueError as e:
            logger.exception(e)
            return None
        isbn_key = u'ISBN:%s' % isbn
        if isbn_key in results:
            book_url = results[isbn_key].get('info_url', '')
            return self._extract_olid_from_url(book_url, url_type="books")
        return None

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
        ol_url_pattern = r'[/]%s[/]([0-9a-zA-Z]+)[/]' % url_type
        try:
            return re.search(ol_url_pattern, url).group(1)
        except AttributeError:
            return None  # No match

    def save_book(self, olid, book, comment):
        pass

    def get_many(self, keys):
        """Get multiple documents in a single request as a dictionary.
        """
        def _get_many(keys):
            url = self.base_url + "/api/get_many"
            response = self.session.get(url, data={'keys': keys})
            return response.json()['result', {}]

        if len(keys) > 500:
            # get in chunks of 500 to avoid crossing the URL length limit.
            d = {}
            for chunk in chunks(keys, 100):
                d.update(self._get_many(chunk))
            return d
        else:
            return self._get_many(keys)

    def save(self, book, comment=None):
        headers = {'Content-Type': 'application/json'}
        data = self.marshal(data)
        if comment:
            headers['Opt'] = '"http://openlibrary.org/dev/docs/api"; ns=42'
            headers['42-comment'] = comment
        data = json.dumps(data)
        return self._request(key, method="PUT", data=data, headers=headers).read()


class Work(object):
    """An aggregate OpenLibrary Work summarizing all Editions of a Book"""

    def __init__(self, key, title=u"", subtitle=None, subject=None,
                 author_name=u"", author_key=None, edition_key=None,
                 language="", publisher=None, publish_date=None,
                 publish_place=None, first_publish_year=None,
                 isbns=None, lccn=None, oclc=None, id_goodreads=None,
                 id_librarything=None, **kwargs):
        """
        Args:
            key (unicode) - a '/<type>/<OLID>' uri, e.g. '/works/OLXXXXXX'
            title (unicode)
            subtitle (unicode) [optional]
            subject (list of unicode) [optional]
            author_name (list of unicode)
            author_key (list of unicode) - list of author OLIDs
            edition_key (list of unicode) - list of edition OLIDs
            language (unicode)
            publisher (list of unicode)
            publish_date (list unicode)
            publish_place (list unicode)
            first_publish_year (int)
            isbns (list unicode)
            lccn (list unicode)
            oclc (list unicode)
            id_goodreads (list unicode)
            id_librarything (list unicode)
        """
        work_olid = [key.rsplit('/', 1)[1]]
        edition_olids = edition_key

        self.title = title
        self.subtitle = subtitle
        self.subjects = subject
        # XXX test that during the zip, author_name and author_key
        # correspond to each other one-to-one, in order
        self.authors = [Author(name=name, olid=author_olid)
                        for (name, author_olid) in
                        zip(author_name or [], author_key or [])]
        self.publishers = publisher
        self.publish_dates = publish_date
        self.publish_places = publish_place
        self.first_publish_year = first_publish_year
        self.edition_olids = edition_olids
        self.language = language

        # These keys all map to [lists] of (usually one) unicode ids
        self.identifiers = {
            'olid': work_olid,
            'isbns': isbns or [],
            'oclc': oclc or [],
            'lccn': lccn or [],
            'goodreads': id_goodreads or [],
            'librarything': id_librarything or []
        }

    def to_book(self):
        publisher = self.publishers[0] if self.publishers else ""
        return Book(title=self.title, subtitle=self.subtitle,
                    identifiers=self.identifiers,
                    authors=self.authors, publisher=publisher,
                    publish_date=self.first_publish_year)


class Results(object):

    """Container for the results of the Search API"""

    def __init__(self, start=0, num_found=0, docs=None, **kwargs):
        self.start = start
        self.num_found = num_found
        self.works = [Work(**work) for work in docs] or []

    @property
    def first(self):
        if self.works:
            return self.works[0]
