"""Test cases for the OpenLibrary module"""


import json
import jsonpickle
import jsonschema
import pytest
import requests
import unittest

from unittest.mock import Mock, call, patch, ANY

from olclient.config import Config
from olclient.common import Author, Book
from olclient.openlibrary import OpenLibrary


def create_edition(ol, **kwargs):
    """Creates a basic test Edition."""
    defaults = {
        'edition_olid': 'OL123M',
        'work_olid': 'OL123W',
        'title': 'Test Title',
        'revision': 1,
        'last_modified': {
            'type': '/type/datetime',
            'value': '2016-10-12T00:48:04.453554',
        },
    }
    defaults.update(kwargs)
    return ol.Edition(**defaults)


def create_work(ol, **kwargs):
    """Creates a basic test Work."""
    defaults = {
        'olid': 'OL123W',
        'title': 'Test Title',
        'revision': 1,
        'last_modified': {
            'type': '/type/datetime',
            'value': '2016-10-12T00:48:04.453554',
        },
    }
    defaults.update(kwargs)
    return ol.Work(**defaults)


def raise_http_error():
    r = requests.Response
    # Non 4xx status will trigger backoff retries
    r.status_code = 404
    kwargs = {'response': r}
    raise requests.HTTPError("test HTTPError", **kwargs)


class TestOpenLibrary(unittest.TestCase):
    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    @patch('requests.Session.get')
    def test_get_olid_by_isbn(self, mock_get):
        isbn_key = 'ISBN:0374202915'
        isbn_bibkeys = {
            isbn_key: {
                'info_url': 'https://openlibrary.org/books/OL23575801M/Marie_LaVeau'
            }
        }
        mock_get.return_value.json.return_value = isbn_bibkeys
        olid = self.ol.Edition.get_olid_by_isbn('0374202915')
        mock_get.assert_called_with(
            f"{self.ol.base_url}/api/books.json?bibkeys={isbn_key}"
        )
        expected_olid = 'OL23575801M'
        self.assertTrue(
            olid == expected_olid, f"Expected olid {expected_olid}, got {olid}"
        )

    @patch('requests.Session.get')
    def test_get_olid_notfound_by_bibkey(self, mock_get):
        mock_get.json_data = {}
        edition = self.ol.Edition.get(isbn='foobar')
        assert edition is None

    @patch('requests.Session.get')
    def test_get_work_by_metadata(self, mock_get):
        doc = {
            "key": "/works/OL2514747W",
            "title": "The Autobiography of Benjamin Franklin",
        }
        search_results = {'start': 0, 'num_found': 1, 'docs': [doc]}
        title = "The Autobiography of Benjamin Franklin"
        mock_get.return_value.json.return_value = search_results
        book = self.ol.Work.search(title=title)
        mock_get.assert_called_with(f"{self.ol.base_url}/search.json?title={title}")
        canonical_title = book.canonical_title
        self.assertTrue(
            'franklin' in canonical_title,
            f"Expected 'franklin' to appear in result title: {canonical_title}",
        )

    @patch('requests.Session.get')
    def test_get_edition_by_isbn(self, mock_get):
        isbn_lookup_response = {
            'ISBN:0374202915': {
                'info_url': 'https://openlibrary.org/books/OL23575801M/Marie_LaVeau'
            }
        }
        edition_response = {'key': "/books/OL23575801M", 'title': 'test'}
        mock_get.return_value.json.side_effect = [
            isbn_lookup_response,
            edition_response,
        ]
        book = self.ol.Edition.get(isbn='0374202915')
        mock_get.assert_has_calls(
            [
                call(f"{self.ol.base_url}/api/books.json?bibkeys=ISBN:0374202915"),
                call().raise_for_status(),
                call().json(),
                call(f"{self.ol.base_url}/books/OL23575801M.json"),
                call().raise_for_status(),
                call().json(),
            ]
        )
        expected_olid = 'OL23575801M'
        self.assertTrue(
            book.olid == expected_olid,
            f"Expected olid {expected_olid}, got {book.olid}",
        )

    @patch('requests.Session.get')
    def test_matching_authors_olid(self, mock_get):
        author_autocomplete = [
            {'name': "Benjamin Franklin", 'key': "/authors/OL26170A"}
        ]
        mock_get.return_value.json.return_value = author_autocomplete
        name = 'Benjamin Franklin'
        got_olid = self.ol.Author.get_olid_by_name(name)
        expected_olid = 'OL26170A'
        self.assertTrue(
            got_olid == expected_olid, f"Expected olid {expected_olid}, got {got_olid}"
        )

    @patch('requests.Session.get')
    def test_create_book(self, mock_get):
        book = Book(
            publisher='Karamanolis',
            title='Alles ber Mikrofone',
            identifiers={'isbn_10': ['3922238246']},
            publish_date=1982,
            authors=[Author(name='Karl Schwarzer')],
            publish_location='Neubiberg bei Mnchen',
        )
        author_autocomplete = [{'name': "Karl Schwarzer", 'key': "/authors/OL7292805A"}]
        mock_get.return_value.json.return_value = author_autocomplete
        got_result = self.ol.create_book(book, debug=True)
        mock_get.assert_called_with(
            f"{self.ol.base_url}/authors/_autocomplete?q=Karl Schwarzer&limit=1"
        )
        expected_result = {
            '_save': '',
            'author_key': '/authors/OL7292805A',
            'author_name': 'Karl Schwarzer',
            'id_name': 'isbn_10',
            'id_value': '3922238246',
            'publish_date': 1982,
            'publisher': 'Karamanolis',
            'title': 'Alles ber Mikrofone',
        }
        self.assertTrue(
            got_result == expected_result,
            f"Expected create_book to return {expected_result}, got {got_result}",
        )

    def test_get_work(self):
        work_json = {'title': 'All Quiet on the Western Front'}
        work = self.ol.Work('OL12938932W', **work_json)
        self.assertTrue(
            work.title.lower() == 'all quiet on the western front',
            "Failed to retrieve work",
        )

    def test_work_json(self):
        authors = [
            {"type": "/type/author_role", "author": {"key": "/authors/OL5864762A"}}
        ]
        work = self.ol.Work('OL12938932W', key='/works/OL12938932W', authors=authors)
        work_json = work.json()
        self.assertEqual(work_json['key'], "/works/OL12938932W")
        self.assertEqual(
            work_json['authors'][0]['author']['key'], "/authors/OL5864762A"
        )

    def test_work_validation(self):
        work = self.ol.Work(
            'OL123W',
            title='Test Title',
            type={'key': '/type/work'},
            revision=1,
            last_modified={
                'type': '/type/datetime',
                'value': '2016-10-12T00:48:04.453554',
            },
        )
        self.assertIsNone(work.validate())

    def test_edition_json(self):
        author = self.ol.Author('OL123A', 'Test Author')
        edition = self.ol.Edition(
            edition_olid='OL123M',
            work_olid='OL123W',
            title='Test Title',
            authors=[author],
        )
        edition_json = edition.json()
        self.assertEqual(edition_json['key'], "/books/OL123M")
        self.assertEqual(edition_json['works'][0], {'key': '/works/OL123W'})
        self.assertEqual(edition_json['authors'][0], {'key': '/authors/OL123A'})

        self.assertNotIn('work_olid', edition_json)
        self.assertNotIn(
            'cover',
            edition_json,
            "'cover' is not a valid Edition property, should be list: 'covers'",
        )

    def test_edition_validation(self):
        author = self.ol.Author('OL123A', 'Test Author')
        edition = self.ol.Edition(
            edition_olid='OL123M',
            work_olid='OL123W',
            title='Test Title',
            type={'key': '/type/edition'},
            revision=1,
            last_modified={
                'type': '/type/datetime',
                'value': '2016-10-12T00:48:04.453554',
            },
            authors=[author],
        )
        self.assertIsNone(edition.validate())
        orphaned_edition = self.ol.Edition(
            edition_olid='OL123M', work_olid=None, title='Test Title', authors=[author]
        )
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            orphaned_edition.validate()

    @patch('requests.Session.get')
    def test_get_notfound(self, mock_get):
        # This tests that if requests.raise_for_status() raises an exception,
        # (e.g. 404 or 500 HTTP response) it is not swallowed by the client.
        mock_get.return_value.raise_for_status = raise_http_error
        suffixes = {'edition': 'M', 'work': 'W', 'author': 'A'}
        for _type, suffix in suffixes.items():
            target = f"OLnotfound{suffix}"
            with pytest.raises(requests.HTTPError):
                _ = self.ol.get(target)
                pytest.fail(f"HTTPError not raised for {_type}: {target}")

    @patch('requests.Session.post')
    def test_save_many(self, mock_post):
        edition = self.ol.Edition(
            edition_olid='OL123M', work_olid='OL12W', title='minimal edition'
        )
        work = self.ol.Work(olid='OL12W', title='minimal work')
        self.ol.save_many([edition, work], "test comment")
        mock_post.assert_called_with(
            f"{self.ol.base_url}/api/save_many", ANY, headers=ANY
        )
        called_with_json = json.loads(mock_post.call_args[0][1])
        called_with_headers = mock_post.call_args[1]['headers']
        assert len(called_with_json) == 2
        self.assertIn('ns=42', called_with_headers['Opt'])
        self.assertEqual('test comment', called_with_headers['42-comment'])

    def test_delete(self):
        delete = self.ol.Delete('OL1W')
        self.assertEqual(delete.olid, 'OL1W')
        self.assertEqual('/type/delete', delete.json()['type']['key'])
        self.assertEqual('/works/OL1W', delete.json()['key'])

    def test_redirect(self):
        redirect = self.ol.Redirect(f='OL1W', t='OL2W')
        self.assertEqual('/type/redirect', redirect.json()['type']['key'])
        self.assertIn('location', redirect.json())


class TestAuthors(unittest.TestCase):
    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    def test_author_validation(self):
        author = self.ol.Author(
            'OL123A',
            name='Test Author',
            revision=1,
            last_modified={
                'type': '/type/datetime',
                'value': '2016-10-12T00:48:04.453554',
            },
        )
        self.assertIsNone(author.validate())


@patch('requests.Session.get')
class TestFullEditionGet(unittest.TestCase):
    # TODO: Expected result includes an empty 'publisher': null, investigate
    target_olid = 'OL3702561M'
    raw_edition = json.loads(
        """{"number_of_pages": 1080, "subtitle": "a modern approach", "series": ["Prentice Hall series in artificial intelligence"], "covers": [92018], "lc_classifications": ["Q335 .R86 2003"], "latest_revision": 6, "contributions": ["Norvig, Peter."], "edition_name": "2nd ed.", "title": "Artificial intelligence", "languages": [{"key": "/languages/eng"}], "subjects": ["Artificial intelligence."], "publish_country": "nju", "by_statement": "Stuart J. Russell and Peter Norvig ; contributing writers, John F. Canny ... [et al.].", "type": {"key": "/type/edition"}, "revision": 6, "publishers": ["Prentice Hall/Pearson Education"], "last_modified": {"type": "/type/datetime", "value": "2010-08-03T18:56:51.333942"}, "key": "/books/OL3702561M", "authors": [{"key": "/authors/OL440500A"}], "publish_places": ["Upper Saddle River, N.J"], "pagination": "xxviii, 1080 p. :", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "dewey_decimal_class": ["006.3"], "notes": {"type": "/type/text", "value": "Includes bibliographical references (p. 987-1043) and index."}, "identifiers": {"librarything": ["43569"], "goodreads": ["27543"]}, "lccn": ["2003269366"], "isbn_10": ["0137903952"], "publish_date": "2003", "works": [{"key": "/works/OL2896994W"}]}"""
    )
    raw_author = json.loads(
        """{"name": "Stuart J. Russell", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "key": "/authors/OL440500A"}"""
    )
    expected = json.loads(
        """{"subtitle": "a modern approach", "series": ["Prentice Hall series in artificial intelligence"], "covers": [92018], "lc_classifications": ["Q335 .R86 2003"], "latest_revision": 6, "contributions": ["Norvig, Peter."], "py/object": "olclient.openlibrary.Edition", "edition_name": "2nd ed.", "title": "Artificial intelligence", "_work": null, "languages": [{"key": "/languages/eng"}], "subjects": ["Artificial intelligence."], "publish_country": "nju", "by_statement": "Stuart J. Russell and Peter Norvig ; contributing writers, John F. Canny ... [et al.].", "type": {"key": "/type/edition"}, "revision": 6, "description": null, "last_modified": {"type": "/type/datetime", "value": "2010-08-03T18:56:51.333942"}, "authors": [{"py/object": "olclient.openlibrary.Author", "bio": null, "name": "Stuart J. Russell", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "identifiers": {}, "olid": "OL440500A"}], "publish_places": ["Upper Saddle River, N.J"], "pages": 1080, "publisher": null, "publishers": ["Prentice Hall/Pearson Education"], "pagination": "xxviii, 1080 p. :", "work_olid": "OL2896994W", "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50.625462"}, "dewey_decimal_class": ["006.3"], "notes": "Includes bibliographical references (p. 987-1043) and index.", "identifiers": {"librarything": ["43569"], "goodreads": ["27543"]}, "lccn": ["2003269366"], "isbn_10": ["0137903952"], "cover": null, "publish_date": "2003", "olid": "OL3702561M"}"""
    )

    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    def test_load_by_isbn(self, mock_get):
        isbn_key = 'ISBN:0137903952'
        isbn_bibkeys = {
            isbn_key: {
                'info_url': "https://openlibrary.org/books/%s/Artificial_intelligence"
                % self.target_olid
            }
        }
        mock_get.return_value.json.side_effect = [
            isbn_bibkeys,
            self.raw_edition.copy(),
            self.raw_author.copy(),
        ]

        actual = json.loads(jsonpickle.encode(self.ol.Edition.get(isbn='0137903952')))
        mock_get.assert_has_calls(
            [
                call(f"{self.ol.base_url}/api/books.json?bibkeys={isbn_key}"),
                call().raise_for_status(),
                call().json(),
                call(f"{self.ol.base_url}/books/{self.target_olid}.json"),
                call().raise_for_status(),
                call().json(),
                call(f"{self.ol.base_url}/authors/OL440500A.json"),
                call().raise_for_status(),
                call().json(),
            ]
        )
        self.expected["py/object"] = actual["py/object"]  # jsonpickle workarounds
        self.expected["authors"][0]["py/object"] = actual["authors"][0]["py/object"]
        self.assertEqual(
            actual,
            self.expected,
            f"Data didn't match for ISBN lookup: \n{actual}\n\nversus:\n\n {self.expected}",
        )

    def test_load_by_olid(self, mock_get):
        mock_get.return_value.json.side_effect = [
            self.raw_edition.copy(),
            self.raw_author.copy(),
        ]

        actual = json.loads(
            jsonpickle.encode(self.ol.Edition.get(olid=self.target_olid))
        )
        mock_get.assert_has_calls(
            [
                call(f"{self.ol.base_url}/books/{self.target_olid}.json"),
                call().raise_for_status(),
                call().json(),
                call(f"{self.ol.base_url}/authors/OL440500A.json"),
                call().raise_for_status(),
                call().json(),
            ]
        )
        self.expected["py/object"] = actual["py/object"]  # jsonpickle workarounds
        self.expected["authors"][0]["py/object"] = actual["authors"][0]["py/object"]
        self.assertEqual(
            actual,
            self.expected,
            f"Data didn't match for olid lookup: {actual}\n\nversus:\n\n {self.expected}",
        )


class TestTextType(unittest.TestCase):
    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()
        self.strings = {'description': 'A String Description', 'notes': 'A String Note'}
        self.texts = {
            'description': {'type': '/type/text', 'value': 'A Text Description'},
            'notes': {'type': '/type/text', 'value': 'A Text Note'},
        }

    def test_edition_text_type_from_string(self):
        edition = create_edition(self.ol, **self.strings)
        self.assertIsNone(edition.validate())
        self.assertIn('type', edition.json()['description'])
        self.assertEqual(edition.json()['description']['value'], "A String Description")

    def test_edition_text_type(self):
        edition = create_edition(self.ol, **self.texts)
        self.assertIsNone(edition.validate())
        self.assertIsInstance(edition.description, str)
        self.assertIn('type', edition.json()['description'])
        self.assertEqual(edition.json()['description']['value'], "A Text Description")

    def test_work_text_type_from_string(self):
        work = create_work(self.ol, **self.strings)
        self.assertIsNone(work.validate())
        self.assertIn('type', work.json()['description'])
        self.assertEqual(work.json()['description']['value'], "A String Description")

    def test_work_text_type(self):
        work = create_work(self.ol, **self.texts)
        self.assertIsNone(work.validate())
        self.assertIsInstance(work.description, str)
        self.assertIn('type', work.json()['description'])
        self.assertEqual(work.json()['description']['value'], "A Text Description")
