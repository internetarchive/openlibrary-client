#-*- encoding: utf-8 -*-

"""Test cases for the OpenLibrary module"""

from __future__ import absolute_import, division, print_function

import json
import jsonpickle
import unittest
import jsonschema

try:
    from mock import Mock, call, patch, ANY
except ImportError:
    from unittest.mock import Mock, call, patch, ANY

from olclient.config import Config
from olclient.common import Author, Book
from olclient.openlibrary import OpenLibrary


class TestOpenLibrary(unittest.TestCase):

    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    @patch('requests.Session.get')
    def test_get_olid_by_isbn(self, mock_get):
        isbn_key = 'ISBN:0374202915'
        isbn_bibkeys = { isbn_key: { 'info_url': 'https://openlibrary.org/books/OL23575801M/Marie_LaVeau' } }
        mock_get.return_value.json.return_value = isbn_bibkeys
        olid = self.ol.Edition.get_olid_by_isbn(u'0374202915')
        mock_get.assert_called_with("%s/api/books.json?bibkeys=%s" % (self.ol.base_url, isbn_key))
        expected_olid = u'OL23575801M'
        self.assertTrue(olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, olid))

    @patch('requests.Session.get')
    def test_get_work_by_metadata(self, mock_get):
        doc = {
            "key":    u"/works/OL2514747W",
            "title":  u"The Autobiography of Benjamin Franklin",
        }
        search_results = { 'start': 0, 'num_found': 1, 'docs': [doc] }
        title = u"The Autobiography of Benjamin Franklin"
        mock_get.return_value.json.return_value = search_results
        book = self.ol.Work.search(title=title)
        mock_get.assert_called_with("%s/search.json?title=%s" % (self.ol.base_url, title))
        canonical_title = book.canonical_title
        self.assertTrue('franklin' in canonical_title,
                        "Expected 'franklin' to appear in result title: %s" % \
                        canonical_title)

    @patch('requests.Session.get')
    def test_get_edition_by_isbn(self, mock_get):
        isbn_lookup_response = { u'ISBN:0374202915': { 'info_url': u'https://openlibrary.org/books/OL23575801M/Marie_LaVeau' } }
        edition_response = { 'key': u"/books/OL23575801M", 'title': 'test' }
        mock_get.return_value.json.side_effect = [isbn_lookup_response, edition_response]
        book = self.ol.Edition.get(isbn=u'0374202915')
        mock_get.assert_has_calls([
            call("%s/api/books.json?bibkeys=ISBN:0374202915" % self.ol.base_url),
            call().json(),
            call("%s%s.json" % (self.ol.base_url, "/books/OL23575801M")),
            call().json()
        ])
        expected_olid = u'OL23575801M'
        self.assertTrue(book.olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, book.olid))

    @patch('requests.Session.get')
    def test_matching_authors_olid(self, mock_get):
        author_autocomplete = [ {'name': u"Benjamin Franklin", 'key': u"/authors/OL26170A"} ]
        mock_get.return_value.json.return_value = author_autocomplete
        name = u'Benjamin Franklin'
        got_olid = self.ol.Author.get_olid_by_name(name)
        expected_olid = u'OL26170A'
        self.assertTrue(got_olid == expected_olid,
                        "Expected olid %s, got %s" % (expected_olid, got_olid))

    @patch('requests.Session.get')
    def test_create_book(self, mock_get):
        book = Book(publisher=u'Karamanolis', title=u'Alles ber Mikrofone',
                    identifiers={'isbn_10': [u'3922238246']}, publish_date=1982,
                    authors=[Author(name=u'Karl Schwarzer')],
                    publish_location=u'Neubiberg bei Mnchen')
        author_autocomplete = [ {'name': u"Karl Schwarzer", 'key': u"/authors/OL7292805A"} ]
        mock_get.return_value.json.return_value = author_autocomplete
        got_result = self.ol.create_book(book, debug=True)
        mock_get.assert_called_with("%s/authors/_autocomplete?q=%s&limit=1" % (self.ol.base_url, "Karl Schwarzer"))
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
                        % (expected_result, got_result))

    def test_get_work(self):
        work_json = {u'title': u'All Quiet on the Western Front'}
        work = self.ol.Work(u'OL12938932W', **work_json)
        self.assertTrue(work.title.lower() == 'all quiet on the western front',
                        "Failed to retrieve work")

    def test_work_json(self):
        authors=[{ "type": "/type/author_role",
                   "author": { "key": "/authors/OL5864762A" }
                }]
        work = self.ol.Work('OL12938932W',
                            key='/works/OL12938932W',
                            authors=authors)
        work_json = work.json()
        self.assertEqual(work_json['key'], "/works/OL12938932W")
        self.assertEqual(work_json['authors'][0]['author']['key'], "/authors/OL5864762A")

    def test_work_validation(self):
        work = self.ol.Work('OL123W',
                            title='Test Title',
                            type={'key': '/type/work'},
                            revision=1,
                            last_modified={
                              'type': '/type/datetime',
                              'value': '2016-10-12T00:48:04.453554'
                            })
        self.assertIsNone(work.validate())

    def test_edition_json(self):
        author = self.ol.Author('OL123A', 'Test Author')
        edition = self.ol.Edition(edition_olid='OL123M',
                                  work_olid='OL123W',
                                  title='Test Title',
                                  authors=[author])
        edition_json = edition.json()
        self.assertEqual(edition_json['key'], "/books/OL123M")
        self.assertEqual(edition_json['works'][0], {'key': '/works/OL123W'})
        self.assertEqual(edition_json['authors'][0], {'key': '/authors/OL123A'})

        self.assertNotIn('work_olid', edition_json)
        self.assertNotIn('cover', edition_json,
                         "'cover' is not a valid Edition property, should be list: 'covers'")

    def test_edition_validation(self):
        author = self.ol.Author('OL123A', 'Test Author')
        edition = self.ol.Edition(edition_olid='OL123M',
                                  work_olid='OL123W',
                                  title='Test Title',
                                  type={'key': '/type/edition'},
                                  revision=1,
                                  last_modified={
                                      'type': '/type/datetime',
                                      'value': '2016-10-12T00:48:04.453554'
                                  },
                                  authors=[author])
        self.assertIsNone(edition.validate())
        orphaned_edition = self.ol.Edition(edition_olid='OL123M',
                                  work_olid=None,
                                  title='Test Title',
                                  authors=[author])
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            orphaned_edition.validate()

    @patch('requests.Session.post')
    def test_save_many(self, mock_post):
        edition = self.ol.Edition(edition_olid='OL123M', work_olid='OL12W', title='minimal edition')
        work    = self.ol.Work(olid='OL12W', title='minimal work')
        self.ol.save_many([edition, work], "test comment")
        mock_post.assert_called_with("%s/api/save_many" % self.ol.base_url, ANY, headers=ANY)
        called_with_json    = json.loads(mock_post.call_args[0][1])
        called_with_headers = mock_post.call_args[1]['headers']
        assert(len(called_with_json) == 2)
        self.assertIn('ns=42', called_with_headers['Opt'])
        self.assertEqual('test comment', called_with_headers['42-comment'])

class TestAuthors(unittest.TestCase):

    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    def test_author_validation(self):
        author = self.ol.Author('OL123A',
                            name='Test Author',
                            revision=1,
                            last_modified={
                              'type': '/type/datetime',
                              'value': '2016-10-12T00:48:04.453554'
                            })
        self.assertIsNone(author.validate())

@patch('requests.Session.get')
class TestFullEditionGet(unittest.TestCase):
    # TODO: Expected result includes an empty 'publisher': null, investigate
    target_olid = u'OL3702561M'
    raw_edition = json.loads("""{"number_of_pages": 1080, "subtitle": "a modern approach", "series": ["Prentice Hall series in artificial intelligence"], "covers": [92018], "lc_classifications": ["Q335 .R86 2003"], "latest_revision": 6, "contributions": ["Norvig, Peter."], "edition_name": "2nd ed.", "title": "Artificial intelligence", "languages": [{"key": "/languages/eng"}], "subjects": ["Artificial intelligence."], "publish_country": "nju", "by_statement": "Stuart J. Russell and Peter Norvig ; contributing writers, John F. Canny ... [et al.].", "type": {"key": "/type/edition"}, "revision": 6, "publishers": ["Prentice Hall/Pearson Education"], "last_modified": {"type": "/type/datetime", "value": "2010-08-03T18:56:51.333942"}, "key": "/books/OL3702561M", "authors": [{"key": "/authors/OL440500A"}], "publish_places": ["Upper Saddle River, N.J"], "pagination": "xxviii, 1080 p. :", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "dewey_decimal_class": ["006.3"], "notes": {"type": "/type/text", "value": "Includes bibliographical references (p. 987-1043) and index."}, "identifiers": {"librarything": ["43569"], "goodreads": ["27543"]}, "lccn": ["2003269366"], "isbn_10": ["0137903952"], "publish_date": "2003", "works": [{"key": "/works/OL2896994W"}]}""")
    raw_author = json.loads("""{"name": "Stuart J. Russell", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "key": "/authors/OL440500A"}""")
    expected = json.loads("""{"subtitle": "a modern approach", "series": ["Prentice Hall series in artificial intelligence"], "covers": [92018], "lc_classifications": ["Q335 .R86 2003"], "latest_revision": 6, "contributions": ["Norvig, Peter."], "py/object": "olclient.openlibrary.Edition", "edition_name": "2nd ed.", "title": "Artificial intelligence", "_work": null, "languages": [{"key": "/languages/eng"}], "subjects": ["Artificial intelligence."], "publish_country": "nju", "by_statement": "Stuart J. Russell and Peter Norvig ; contributing writers, John F. Canny ... [et al.].", "type": {"key": "/type/edition"}, "revision": 6, "last_modified": {"type": "/type/datetime", "value": "2010-08-03T18:56:51.333942"}, "authors": [{"py/object": "olclient.openlibrary.Author", "bio": "", "name": "Stuart J. Russell", "links": [], "created": "2008-04-01T03:28:50.625462", "identifiers": {}, "alternate_names": [], "birth_date": "", "olid": "OL440500A"}], "publish_places": ["Upper Saddle River, N.J"], "pages": 1080, "publisher": null, "publishers": ["Prentice Hall/Pearson Education"], "pagination": "xxviii, 1080 p. :", "work_olid": "OL2896994W", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "dewey_decimal_class": ["006.3"], "notes": {"type": "/type/text", "value": "Includes bibliographical references (p. 987-1043) and index."}, "identifiers": {"librarything": ["43569"], "goodreads": ["27543"]}, "lccn": ["2003269366"], "isbn_10": ["0137903952"], "cover": null, "publish_date": "2003", "olid": "OL3702561M"}""")
        
    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    def test_load_by_isbn(self, mock_get):
        isbn_key = 'ISBN:0137903952'
        isbn_bibkeys = { isbn_key: { 'info_url': "https://openlibrary.org/books/%s/Artificial_intelligence" % self.target_olid } }
        mock_get.return_value.json.side_effect = [isbn_bibkeys, self.raw_edition.copy(), self.raw_author.copy()]

        actual = json.loads(jsonpickle.encode(self.ol.Edition.get(isbn=u'0137903952')))
        mock_get.assert_has_calls([
            call("%s/api/books.json?bibkeys=%s" % (self.ol.base_url, isbn_key)),
            call().json(),
            call("%s/books/%s.json" % (self.ol.base_url, self.target_olid)),
            call().json(),
            call("%s/authors/OL440500A.json" % self.ol.base_url),
            call().json()
        ])
        self.assertEquals(actual, self.expected,
                        "Data didn't match for ISBN lookup: \n%s\n\nversus:\n\n %s" % (actual, self.expected))

    def test_load_by_olid(self, mock_get):
        mock_get.return_value.json.side_effect = [self.raw_edition.copy(), self.raw_author.copy()]

        actual = json.loads(jsonpickle.encode(self.ol.Edition.get(olid=self.target_olid)))
        mock_get.assert_has_calls([
            call("%s/books/%s.json" % (self.ol.base_url, self.target_olid)),
            call().json(),
            call("%s/authors/OL440500A.json" % self.ol.base_url),
            call().json()
        ])
        self.assertEquals(actual, self.expected,
                        "Data didn't match for olid lookup: %s\n\nversus:\n\n %s" % (actual, self.expected))
