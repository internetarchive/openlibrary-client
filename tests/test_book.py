#-*- encoding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import os
import unittest

from olclient.book import Book


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
