#-*- encoding: utf-8 -*-

"""Utility for parsing and inter-converting various types of MARC records"""

from __future__ import absolute_import, division, print_function

import subprocess
import tempfile

import pymarc

from .openlibrary import common
from .utils import chunks, has_unicode


class MARCRecord(dict):

    """An alternate dict representation of pymarc.Record keys by its MARC
    field number so contents of each field can be parsd without having
    to traverse the datastructure each time.
    """

    # TODO: 250 (a) is edition
    # http://www.loc.gov/marc/bibliographic/bd250.html

    AUTHOR_MAPPING = [
        ('a', 'author_name')
    ]

    PUBLISHER_MAPPING = [
        ('a', 'publish_location'),
        ('b', 'publisher'),
        ('c', 'publish_date')
    ]

    TITLE_MAPPING = [
        ('a', 'title'),
        ('b', 'subtitle')
    ]

    def __init__(self, pymarc_record):
        """MARCRecord takes a pymarc Record (i.e. a single marc entry) and
        parses it into a dictionary of fields, keyed by MARC Field
        numbers. This way, each line of fields can be easily accessed in a
        single pass and mapped to a human readable name via a
        property. Otherwise, pymarc Records don't offer an intuitive way
        to access fields like `publisher`.

        Args:
            pymarc_record (pymarc.Record)
        """
        fields = dict((field.tag, field.subfields)
                      for field in pymarc_record.fields
                      if hasattr(field, 'subfields'))
        for k in fields:
            setattr(self, k, fields[k])

    @property
    def author(self):
        """http://www.loc.gov/marc/bibliographic/bd100.html

        Returns:
            A (dict) of the keys specified in the right tuple entries
            of the AUTHOR_MAPPING, mapped to their respective values
            from the MARC field segments associated with the left side
            of the AUTHOR_MAPPING. e.g. {'author_name': u'Benjamin Franklin'}
        """
        author = self.parse_fields('100', self.AUTHOR_MAPPING)
        author_name = author.get(u'author_name', u'')
        if author_name:
            author_name = ' '.join(author_name.split(', ')[::-1])
        return common.Author(name=author_name)

    @property
    def publisher(self):
        """http://www.loc.gov/marc/bibliographic/bd260.html

        Returns:
            A (dict) of the keys specified in the right tuple entries
            of the PUBLISHER_MAPPING, mapped to their respective values
            from the MARC field segments associated with the left side
            of the PUBLISHER_MAPPING. e.g.
            {'publisher': u'Penguin', 'publisher_location': u'NY, ...}
        """
        return self.parse_fields('260', self.PUBLISHER_MAPPING)

    @property
    def title(self):
        """http://www.loc.gov/marc/bibliographic/bd245.html

        Returns:
            A (dict) containing the title of this marc record,
            as well as a subtitle if available (see TITLE_MAPPING)
        """
        return self.parse_fields('245', self.TITLE_MAPPING)

    def parse_fields(self, _id, mapping):
        """Performs a dict lookup of the marc record's fields by field name to
        retrieve a set of values in that field. These field values are
        then marshaled into a dictionary of subfields mapped to their
        values. Finally, a mapping is applied to translate these
        cripticly named marc subfields into the human readable
        versions specified within the mapping.

        Args:
            _id (unicode) - the primary key / number of the MARC field
                            (generally a number), e.g. '245' for title info.
                            See valid field primary keys at:
                            http://www.loc.gov/marc/bibliographic
            mapping (dict) - a mapping of MARC record field subfield keys to
                             human readable keys

        Returns:
            A (dict) whose keys are the human readable components of the mapping
            and whose values are extracted from the MARC record field.

        Usage:
            >>> keyed_record.parse_fields('100', self.AUTHOR_MAPPING)
            {u'author_name': u'Benjamin Franklin'}
        """
        data = {}

        if not hasattr(self, _id):
            return data

        subfields = getattr(self, _id)
        fieldmap = dict(chunks(subfields, 2))

        for key, value in mapping:
            if key in fieldmap:
                data[value] = fieldmap[key]
        return data


class MARC(object):

    """Convert between MARC formats"""

    @classmethod
    def line_to_dict(cls, line_marc):
        """A 1-hop convenience method for turning a "display tagged" line marc
        file into a dictionary of human readable values

        Args:
            line_marc - marc record contents in line display format
        """
        bin_marc = cls.convert(line_marc, outformat='marc')
        return cls.to_dict(bin_marc)

    @classmethod
    def to_dict(cls, bin_marc):
        """Takes binary marc or marcxml and parses it into a human readable
        dict by first creating a pymarc object which enables easy
        access to the marc's fields and data.  Pymarc doesn't have a
        convenient way to cast itself to a dict (keyed) with
        meaningful values (e.g. title, isbn, etc) so this method
        converts pymarc's Record (pymarc.record.Record) to a human
        readable dict.
        """
        reader = pymarc.MARCReader(bin_marc, hide_utf8_warnings=True,
                                   force_utf8=True, utf8_handling='ignore')
        record = reader.next()
        keyed_record = MARCRecord(record)
        data = {
            'identifiers': {},
            'authors': [keyed_record.author],
        }
        isbn = record.isbn()
        if isbn:
            data['isbn_%s' % len(record.isbn())] = [record.isbn()]
        data.update(keyed_record.publisher)
        data.update(keyed_record.title)
        return data

    @staticmethod
    def convert(marc, informat='line', outformat='marc'):
        """Convert MARCs of various format to other formats by shelling out to
        the `yaz-marcdump` utility. By default, converts the line 'tagged
        display' format to binary marc.

        Args:
            marc (unicode) - contents of a MARC (of type `informat`)
            informat (unicode) - convert from this type (a yaz flag)
            outformat (unicode) - convert to this format (a yaz flag)
        """
        with tempfile.NamedTemporaryFile(delete=True, suffix=u'.txt') as tmp:
            unicode_marc = marc if has_unicode(marc) else marc.encode("utf-8")
            tmp.write(unicode_marc)
            tmp.seek(0)
            new_marc = subprocess.check_output([
                u'yaz-marcdump', '-i', informat, '-o', outformat, tmp.name
            ])
            return new_marc

    @classmethod
    def line_to_book(cls, line_marc):
        """Converts a line (display format) MARC record (i.e. human readable)
        into a standardized Book object.

        See: openlibrary-client/examples/marc/line_marc.txt
        """
        bin_marc = cls.convert(line_marc)
        return cls.to_book(bin_marc)

    @classmethod
    def to_book(cls, bin_marc):
        """Creates a Book object from a marc file (of specified format)

        Args:
            marc (unicode) - contents of the marc
            fmt (unicode) - binary "marc", display "line", or "marcxml"

        Returns:
            (common.Book)
        """
        marc_dict = cls.to_dict(bin_marc)
        return common.Book(**marc_dict)
