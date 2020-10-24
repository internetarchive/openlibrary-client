import six

import os
import unittest

import pymarc

from olclient.marc import MARC, MARCRecord


EXAMPLES_PATH = os.path.abspath(
    os.path.join(
        os.path.join(
            os.path.join(
                os.path.join(
                    os.path.abspath(__file__),
                    os.pardir),
                os.pardir),
            'examples'),
        'marc'))


example_path = lambda filename: os.path.join(EXAMPLES_PATH, filename)


class TestMARC(unittest.TestCase):

    def test_convert_line_to_bin(self):
        with open(example_path('line_marc.txt')) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            with open(example_path('bin_marc.mrc'), 'rb') as expected_bin_marc:
                self.assertEqual(bin_marc, expected_bin_marc.read(),
                                "output of convert (line->bin) "
                                "didn't match example file")

    def test_line_to_dict(self):
        """Also tests MARC.to_dict(marc)"""
        with open(example_path('line_marc.txt')) as line_marc:
            data = MARC.line_to_dict(line_marc.read())
            expected_title = "Wege aus einer kranken Gesellschaft"
            self.assertEqual(data['title'], expected_title,
                            "Expected title %s, got %s"
                            % (expected_title, data['title']))

    def test_line_marc_to_book(self):
        with open(os.path.join(EXAMPLES_PATH, 'line_marc.txt')) as line_marc:
            book = MARC.line_to_book(line_marc.read())
            expected_title = "Wege aus einer kranken Gesellschaft"
            self.assertEqual(book.title, expected_title,
                            "Expected title %s, got title %s"
                            % (expected_title, book.title))

    def test_bin_marc_to_book(self):
        with open(os.path.join(EXAMPLES_PATH, 'line_marc.txt')) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            book = MARC.to_book(bin_marc)
            expected_title = "Wege aus einer kranken Gesellschaft"
            self.assertEqual(book.title, expected_title,
                            "Expected title %s, got title %s"
                            % (expected_title, book.title))

    def test_MARCRecord(self):
        with open(os.path.join(EXAMPLES_PATH, 'line_marc.txt')) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            reader = pymarc.MARCReader(bin_marc, hide_utf8_warnings=True,
                                       force_utf8=True, utf8_handling='ignore')
            keyed_record = MARCRecord(next(reader))
            self.assertTrue(keyed_record.author.name,
                            "Failed to retrieve author name")


    def test_line_to_bin_unicode(self):
        line_marc_file = example_path('line_marc_unicode.txt')
        bin_marc_file = example_path('bin_marc_unicode.mrc')
        with open(line_marc_file) as line_marc:
            bin_marc = MARC.convert(line_marc.read())
            with open(bin_marc_file, 'rb') as expected_bin_marc:
                self.assertEqual(bin_marc, expected_bin_marc.read(),
                                "Binary MARC didn't match expected " \
                                "unicode content")
                marcs = pymarc.MARCReader(bin_marc, hide_utf8_warnings=True,
                                          force_utf8=True, utf8_handling='ignore')
                marc = next(marcs)
                self.assertEqual(marc.author(),
                                'ƀƁƂƃƄƅƆƇƈƉƊƋƌƍƎƏƐƑƒƓƔƕƖƘƙƚƛƜƝƞƟƠơ '\
                                '1900-1980 Verfasser (DE-588)118536389 aut',
                                "Line MARC title didn't match pymarc title")

    def test_unicode_line_marc_to_book(self):
        line_marc_file = example_path('line_marc_unicode.txt')
        with open(line_marc_file) as line_marc:
            book = MARC.line_to_book(line_marc.read())
            expected_author = 'ƀƁƂƃƄƅƆƇƈƉƊƋƌƍƎƏƐƑƒƓƔƕƖƘƙƚƛƜƝƞƟƠơ'
            expected_title = 'ΛΦϞЌЍЖ⁁⅀∰   ﬢﬡ－中英字典こんにちはß'
            self.assertEqual(book.primary_author.name, expected_author,
                            "Expected author %s, got author %s" % \
                            (expected_author, book.primary_author.name))
            self.assertEqual(book.primary_author.name, expected_author,
                            "Expected title %s, got title %s" % \
                            (expected_title, book.title))
