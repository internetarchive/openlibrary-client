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
            'examples'),
        'xisbn'))


example_path = lambda filename: os.path.join(EXAMPLES_PATH, filename)


XISBN_BOOKS = [
    Book(authors= [Author(name='Carl Bridenbaugh.')], cover= '',
         identifiers={
             'isbn_10': ['0689705344'],
             'lccn': ['78152044'],
             'oclc': ['4128493', '466349680',
                      '6066278', '730964000', '803233939']
         }, language='eng', pages=None, publish_date= '1976',
         publisher='Atheneum', subtitle='',
         title= 'Fat mutton and liberty of conscience : society in Rhode Island, 1636-1690'),
    Book(authors=[Author(name='Carl Bridenbaugh.')],         
         identifiers={
             'isbn_10': ['0571097987'],
             'lccn': [],
             'oclc': ['245795534', '462738208', '5953546', '751297386',
                      '803090541', '860291849']
         },
         language='eng', pages= None, publish_date= '1972',
         cover='', publisher='Faber and Faber', subtitle='',
         title= 'Extraterritorial : papers on literature and the language revolution')
]



class TestBook(unittest.TestCase):

    def test_create_book(self):
        book = Book(title="Test Book", authors=["Jane Doe"], publish_date=2015)
        self.assertTrue(book.title == "Test Book",
                        "Book title should be %s, instead is %s" %
                        ("Test Book", book.title))

        self.assertTrue(book.authors[0] == "Jane Doe",
                        "Book author should be %s, instead is %s" %
                        ("Jane Doe", book.authors))

        self.assertTrue(book.publish_date == 2015,
                        "Book year should be %s, instead is %s" %
                        (2015, book.publish_date))

    def test_canonical_title(self):
        """This also effectively tests `book.rm_punctuation`"""
        book = Book(title="The Autobiography of: Benjamin Franklin")
        expected = "the autobiography of benjamin franklin"
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
