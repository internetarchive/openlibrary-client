# Change the Python Run Time Path
import sys

sys.path.insert(0, '../')

# Import necessary libraries to use
from olclient.openlibrary import OpenLibrary
import olclient.common as common


def main():
    # Defining an Open Library Object
    ol = OpenLibrary()

    # Define a Book Object
    book = common.Book(
        title="Warlight: A novel",
        authors=[common.Author(name="Michael Ondaatje")],
        publisher="Deckle Edge",
        publish_date="2018",
    )

    # Add metadata like ISBN 10 and ISBN 13
    book.add_id('isbn_10', '0525521194')
    book.add_id('isbn_13', '978-0525521198')

    # Create a new book
    new_book = ol.create_book(book)

    # Add a book cover for the given book
    new_book.add_bookcover(
        'https://images-na.ssl-images-amazon.com/images/I/51kmM%2BvVRJL._SX337_BO1,204,203,200_.jpg'
    )


if __name__ == '__main__':
    main()
