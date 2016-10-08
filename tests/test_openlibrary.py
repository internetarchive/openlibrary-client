#-*- encoding: utf-8 -*-

"""Test cases for the OpenLibrary module"""

from __future__ import absolute_import, division, print_function

import unittest

from olclient.config import Config
from olclient.common import Author, Book
from olclient.openlibrary import OpenLibrary


class TestOpenLibrary(unittest.TestCase):

    def setUp(self):
        ol_config = Config().get_config()['openlibrary']
        ol_creds = ol_config.get('credentials')
        self.ol = OpenLibrary(credentials=ol_creds)

    def test_get_olid_by_isbn(self):
        olid = self.ol.get_olid_by_isbn(u'0374202915')
        expected_olid = u'OL23575801M'
        self.assertTrue(olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, olid))

    def test_get_book_by_metadata(self):
        title = u"The Autobiography of Benjamin Franklin"
        book = self.ol.get_book_by_metadata(title=title)
        canonical_title = book.canonical_title
        self.assertTrue('franklin' in canonical_title,
                        "Expected 'franklin' to appear in result title: %s" % \
                        canonical_title)

    def test_get_book_by_isbn(self):
        book = self.ol.get_book_by_isbn(u'0374202915')
        book_olid = book.identifiers['olid'][0]
        expected_olid = u'OL23575801M'
        self.assertTrue(book_olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, book_olid))

    def test_matching_authors_olid(self):
        name = u'Benjamin Franklin'
        got_olid = self.ol.Author.get_olid_by_name(name)
        expected_olid = u'OL26170A'
        self.assertTrue(got_olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, got_olid))

    def test_create_book(self):
        book = Book(publisher=u'Karamanolis', title=u'Alles ber Mikrofone',
                    identifiers={'isbn_10': [u'3922238246']}, publish_date=1982,
                    authors=[Author(name=u'Karl Schwarzer')],
                    publish_location=u'Neubiberg bei Mnchen')
        got_result = self.ol.create_book(book, debug=True)
        expected_result = {
            '_save': '',
            'author_key': u'/authors/OL7292805A',
            'author_name': u'Karl Schwarzer',
            'id_name': 'isbn_10',
            'id_value': u'3922238246',
            'publish_date': 1982,
            'publisher': u'Karamanolis',
            'title': u'Alles ber Mikrofone'
        }
        self.assertTrue(got_result == expected_result,
                        "Expected create_book to return %s, got %s" \
                        % (got_result, expected_result))
