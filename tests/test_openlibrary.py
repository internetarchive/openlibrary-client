#-*- encoding: utf-8 -*-

"""Test cases for the OpenLibrary module"""

from __future__ import absolute_import, division, print_function

import json
import jsonpickle
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
        olid = self.ol.Edition.get_olid_by_isbn(u'0374202915')
        expected_olid = u'OL23575801M'
        self.assertTrue(olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, olid))

    def test_get_work_by_metadata(self):
        title = u"The Autobiography of Benjamin Franklin"
        book = self.ol.Work.search(title=title)
        canonical_title = book.canonical_title
        self.assertTrue('franklin' in canonical_title,
                        "Expected 'franklin' to appear in result title: %s" % \
                        canonical_title)

    def test_get_edition_by_isbn(self):
        book = self.ol.Edition.get(isbn=u'0374202915')
        expected_olid = u'OL23575801M'
        self.assertTrue(book.olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, book.olid))

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

    def test_get_work(self):
        work = self.ol.Work.get(u'OL12938932W')
        self.assertTrue(work.title.lower() == 'all quiet on the western front',
                        "Failed to retrieve work")

    def test_get_list(self):
        lst = self.ol.List.get(username=u'mekBot', olid=u'OL102669L')
        self.assertTrue(lst.name == u'Building Habits',
                        'Failed to get the correct list')
        
    def test_get_lists(self):
        lsts = self.ol.List.get(username=u'mekBot')
        self.assertTrue(any([lst.olid == u'OL102669L' for lst in lsts]),
                        'Failed to find correct list')

    def test_create_delete_lists(self):
        lst = self.ol.List.create(u'OL16747834W', name="test")
        lst2 = None
        olid = lst.olid
        lst.delete()
        try:
            lst2 = self.ol.List.get(olid=olid)
        except Exception:
            pass
        self.assertTrue(lst2 is None, 'List %s should have been deleted' % olid)
            
    def test_cli(self):
        expected = json.loads("""{"subtitle": "a modern approach", "series": ["Prentice Hall series in artificial intelligence"], "covers": [92018], "lc_classifications": ["Q335 .R86 2003"], "latest_revision": 6, "contributions": ["Norvig, Peter."], "py/object": "olclient.openlibrary.Edition", "edition_name": "2nd ed.", "title": "Artificial intelligence", "_work": null, "languages": [{"key": "/languages/eng"}], "subjects": ["Artificial intelligence."], "publish_country": "nju", "by_statement": "Stuart J. Russell and Peter Norvig ; contributing writers, John F. Canny ... [et al.].", "type": {"key": "/type/edition"}, "revision": 6, "description": "", "last_modified": {"type": "/type/datetime", "value": "2010-08-03T18:56:51.333942"}, "authors": [{"py/object": "olclient.openlibrary.Author", "bio": "", "name": "Stuart J. Russell", "links": [], "created": "2008-04-01T03:28:50.625462", "identifiers": {}, "alternate_names": ["Stuart; Norvig, Peter Russell"], "birth_date": "", "olid": null}], "publish_places": ["Upper Saddle River, N.J"], "pages": 1080, "publisher": ["Prentice Hall/Pearson Education"], "pagination": "xxviii, 1080 p. :", "work_olid": "OL2896994W", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "dewey_decimal_class": ["006.3"], "notes": {"type": "/type/text", "value": "Includes bibliographical references (p. 987-1043) and index."}, "identifiers": {"librarything": ["43569"], "goodreads": ["27543"]}, "cover": "", "publish_date": "2003", "olid": "OL3702561M"}""")
        actual = json.loads(jsonpickle.encode(self.ol.Edition.get(isbn=u'0137903952')))
        self.assertTrue(actual == expected,
                        "Data didn't match: \n%s\n\nversus:\n\n %s" % (actual, expected))
        actual = json.loads(jsonpickle.encode(self.ol.Edition.get(olid=u'OL3702561M')))
        self.assertTrue(actual == expected,
                        "Data didn't match: %s\n\nversus:\n\n %s" % (actual, expected))
