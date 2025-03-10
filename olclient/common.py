"""General project independent data structure for enabling
interoperability between OpenLibrary and partner services + data
sources"""


from olclient.utils import rm_punctuation

VALID_IDENTIFIERS = (
    'olid',
    'oclc',
    'isbn_10',
    'isbn_13',
    'isbns',
    'lccn',
    'goodreads',
    'librarything',
    'wikidata',
    'bookbrainz',
)


class Entity:
    def __init__(self, identifiers):
        if identifiers is not None:
            self._validate_identifiers(identifiers)
        self.identifiers = identifiers or {}

    @staticmethod
    def _validate_identifiers(identifiers):
        for id_type, values in identifiers.items():
            if id_type not in VALID_IDENTIFIERS:
                raise AttributeError(
                    f"ID type '{id_type}' is not one of {VALID_IDENTIFIERS}"
                )
            if type(values) not in (list, tuple):
                raise TypeError("Identifier values must be lists")

    def add_id(self, id_type, identifier):
        """Adds an identifier to this book

        Args:
            id_type (unicode) - valid identifier types:
              [u'olid', u'oclc', u'isbns']

        Usage:
             >>> book.identifiers
             {'olid': [u'OL2514725W']}
             >>> book.add_id(u'oclc', u'4963507')
             {'olid': [u'OL2514725W'], 'oclc': [u'4963507']}
             >>> book.add_id(u'olid', u'OL20536769M')
             {'olid': [u'OL2514725W', u'OL20536769M'], 'oclc': [u'4963507']}
        """
        _ids = {identifier}
        if id_type in self.identifiers:
            _ids = _ids.union(self.identifiers.get(id_type, []))

        self.identifiers[id_type] = list(_ids)
        return self.identifiers

    def __repr__(self):
        return f'<{str(self.__class__)[1:-1]} {self.__dict__}>'


class Author(Entity):
    """Represents a book Author and their identifier on a service
    (currently only OpenLibrary -- this should be refactored to
    include multiple identifiers, such as wikidata ID (see
    Book.identifiers), as well as other RDFA Author fields like date
    of birth, etc

    TODO: Consider moving to own file
    """

    def __init__(self, name, identifiers=None, **kwargs):
        super().__init__(identifiers=identifiers)
        self._validate_name(name)
        self.name = name

        for kwarg in kwargs:
            setattr(self, kwarg, kwargs[kwarg])

    def __repr__(self):
        return f'<{str(self.__class__)[1:-1]} {self.__dict__}>'

    @staticmethod
    def _validate_name(name):
        if ',' in name:
            raise ValueError(
                f"{name} is not a valid Author name - No commas allowed (first last)"
            )


class Book(Entity):
    """Organizational model for standardizing MARC, OpenLibrary, and other
    sources into a uniform format so they can be programmatically
    ingested and compared for similarity.
    """

    def __init__(
        self,
        title,
        subtitle="",
        identifiers=None,
        number_of_pages=None,
        authors=None,
        publisher=None,
        publish_date="",
        cover="",
        **kwargs,
    ):
        """
        Args:
            title (unicode) [required]
            subtitle (unicode) [optional]

            identifiers (list) - a dict of id_types mapped to lists of
                                 (unicode) ids of this type:
                                 e.g. {'olid': [u'OL...', u'OL...']}
            pages (int)
            authors (list of Author)
            publisher (list of unicode)
            publish_date (int) - year
            cover (unicode) - uri of bookcover
        """
        super().__init__(identifiers=identifiers)
        self.title = title
        self.subtitle = subtitle
        self.pages = number_of_pages
        self.authors = authors or []
        self.publisher = publisher
        self.publish_date = publish_date
        self.cover = cover

        for kwarg in kwargs:
            setattr(self, kwarg, kwargs[kwarg])

    def __repr__(self):
        return f'<{str(self.__class__)[1:-1]} {self.__dict__}>'

    @property
    def canonical_title(self):
        """Make book titles homogeneous so they can be compared canonically

        Usage:
            >>> book = Book(title=u"The Autobiography of: Benjamin Franklin")
            >>> book.canonical_title

        """
        title = self.title.lower()
        title = rm_punctuation(title)
        return title

    @property
    def primary_author(self):
        """If multiple authors are present in this book, extract the 1st
        Author object (if it exists) or return None
        """
        try:
            return self.authors[0]
        except IndexError:
            return None

    @classmethod
    def xisbn_to_isbns(cls, xisbn):
        isbns = []
        editions = xisbn.get('list', [])
        for ed in editions:
            isbns.extend(ed.get('isbn', []))
        return isbns

    @classmethod
    def xisbn_to_books(cls, xisbn):
        books = []
        editions = xisbn.get('list', [])
        for ed in editions:
            isbns = ed.get('isbn', [])
            book = cls(
                title=ed.get('title', ''),
                authors=[Author(name=ed.get('author', ''))],
                publisher=ed.get('publisher', ''),
                identifiers={
                    'oclc': ed.get('oclcnum', []),
                    'lccn': ed.get('lccn', []),
                },
                language=ed.get('lang', ''),
                publish_date=ed.get('year', None),
            )
            for isbn in isbns:
                book.add_id(f'isbn_{len(isbn)}', isbn)
            books.append(book)
        return books
