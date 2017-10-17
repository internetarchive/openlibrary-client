#-*- encoding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import json
import os
import unittest

from olclient.common import Book, Author

EXAMPLES_PATH = os.path.abspath(
    os.path.join(
        os.path.join(
            os.path.join(
                os.path.join(
                    os.path.abspath(__file__),
                    os.pardir),
                os.pardir),
            u'examples'),
        u'xisbn'))


example_path = lambda filename: os.path.join(EXAMPLES_PATH, filename)


XISBN_BOOKS = [
    Book(authors= [Author(name=u'Carl Bridenbaugh.')], cover= '',
         identifiers={
             'isbn_10': [u'0689705344'],
             'lccn': [u'78152044'],
             'oclc': [u'4128493', u'466349680',
                      u'6066278', u'730964000', u'803233939']
         }, language=u'eng', pages=None, publish_date= u'1976',
         publisher=u'Atheneum', subtitle=u'',
         title= u'Fat mutton and liberty of conscience : society in Rhode Island, 1636-1690'),
    Book(authors=[Author(name=u'Carl Bridenbaugh.')],         
         identifiers={
             'isbn_10': [u'0571097987'],
             'lccn': [],
             'oclc': [u'245795534', u'462738208', u'5953546', u'751297386',
                      u'803090541', u'860291849']
         },
         language=u'eng', pages= None, publish_date= u'1972',
         cover=u'', publisher=u'Faber and Faber', subtitle=u'',
         title= u'Extraterritorial : papers on literature and the language revolution')
]



class TestBook(unittest.TestCase):

    def test_create_book(self):
        book = Book(title="Test Book", author="Jane Doe", year=2015)
        self.assertTrue(book.title == "Test Book",
                        "Book title should be %s, instead is %s" %
                        ("Test Book", book.title))

        self.assertTrue(book.author == "Jane Doe",
                        "Book author should be %s, instead is %s" %
                        ("Jane Doe", book.author))

        self.assertTrue(book.year == 2015,
                        "Book year should be %s, instead is %s" %
                        (2015, book.year))

    def test_canonical_title(self):
        """This also effectively tests `book.rm_punctuation`"""
        book = Book(title=u"The Autobiography of: Benjamin Franklin")
        expected = u"the autobiography of benjamin franklin"
        got = book.canonical_title
        self.assertTrue(got == expected,
                        "Title canonicalization expected %s, got %s" \
                        % (expected, got))

    def test_xisbn_to_books(self):
        with open(example_path('0140551042_xisbn.json')) as _xisbn:
            xisbn = json.load(_xisbn)
            books = Book.xisbn_to_books(xisbn)
            self.assertTrue(len(books) == len(XISBN_BOOKS))
            for i in range(len(books)):

                self.assertTrue(books[i].title == XISBN_BOOKS[i].title,
                                "Got title %s, expected title %s" % \
                                (books[i].title, XISBN_BOOKS[i].title))

                self.assertTrue([books[i].authors[k].name == \
                                 XISBN_BOOKS[i].authors[k].name
                                 for k in range(len(books[i].authors))],
                                "Got authors %s \n expected authors %s" % \
                                (books[i].authors, XISBN_BOOKS[i].authors))

                self.assertTrue(books[i].publisher == XISBN_BOOKS[i].publisher,
                                "Got publisher %s, expected publisher %s" % \
                                (books[i].publisher, XISBN_BOOKS[i].publisher))

                self.assertTrue(books[i].identifiers == XISBN_BOOKS[i].identifiers,
                                "Got identifiers %s, expected identifiers %s" % \
                                (books[i].identifiers, XISBN_BOOKS[i].identifiers))

                self.assertTrue(books[i].publish_date == XISBN_BOOKS[i].publish_date,
                                "Got publish_date %s, expected publish_date %s" % \
                                (books[i].publish_date, XISBN_BOOKS[i].publish_date))
