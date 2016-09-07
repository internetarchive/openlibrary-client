#-*- encoding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import os
import unittest

import pymarc

from olclient.book import Author, Book
from olclient.marc import MARC, MARCRecord


EXAMPLES_PATH = os.path.abspath(
    os.path.join(
        os.path.join(
            os.path.join(
                os.path.join(
                    os.path.abspath(__file__),
                    os.pardir),
                os.pardir),
            u'examples'),
        u'marc'))


example_path = lambda filename: os.path.join(EXAMPLES_PATH, filename)


class TestMARC(unittest.TestCase):

    def test_convert_line_to_bin(self):
        with open(example_path('line_marc.txt')) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            with open(example_path('bin_marc.mrc')) as expected_bin_marc:
                self.assertTrue(bin_marc == expected_bin_marc.read(),
                                "output of convert (line->bin) "
                                "didn't match example file")

    def test_line_to_dict(self):
        """Also tests MARC.to_dict(marc)"""
        with open(example_path('line_marc.txt')) as line_marc:
            data = MARC.line_to_dict(line_marc.read())
            expected_title = "Wege aus einer kranken Gesellschaft"
            self.assertTrue(data['title'] == expected_title,
                            "Expected title %s, got %s"
                            % (expected_title, data['title']))


    def test_line_marc_to_book(self):
        with open(os.path.join(EXAMPLES_PATH, 'line_marc.txt')) as line_marc:
            book = MARC.line_to_book(line_marc.read())
            expected_title = "Wege aus einer kranken Gesellschaft"
            self.assertTrue(book.title == expected_title,
                            "Expected title %s, got title %s"
                            % (expected_title, book.title))

    def test_bin_marc_to_book(self):
        with open(os.path.join(EXAMPLES_PATH, 'line_marc.txt')) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            book = MARC.to_book(bin_marc)
            expected_title = "Wege aus einer kranken Gesellschaft"
            self.assertTrue(book.title == expected_title,
                            "Expected title %s, got title %s"
                            % (expected_title, book.title))

    def test_MARCRecord(self):
        with open(os.path.join(EXAMPLES_PATH, 'line_marc.txt')) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            reader = pymarc.MARCReader(bin_marc, hide_utf8_warnings=True,
                                       force_utf8=True, utf8_handling='ignore')
            keyed_record = MARCRecord(reader.next())            
            self.assertTrue(keyed_record.author.name,
                            "Failed to retrieve author name")
