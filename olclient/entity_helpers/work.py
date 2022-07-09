from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Optional, Any

import backoff
from requests import Response

from olclient.common import Entity, Book
from olclient.helper_classes.results import Results
from olclient.utils import merge_unique_lists, get_text_value, get_approval_from_cli

logger = logging.getLogger('open_library_work')


def get_work_helper_class(ol_context):
    class Work(Entity):

        OL = ol_context

        def __init__(self, olid: str, identifiers=None, **kwargs):
            super().__init__(identifiers)
            self.olid = olid
            self._editions: List = []
            self.description = get_text_value(kwargs.pop('description', None))
            self.notes = get_text_value(kwargs.pop('notes', None))
            for kwarg in kwargs:
                setattr(self, kwarg, kwargs[kwarg])

        def json(self) -> dict:
            """Returns a dict JSON representation of an OL Work suitable
            for saving back to Open Library via its APIs.
            """
            exclude = ['_editions', 'olid']
            data = {k: v for k, v in self.__dict__.items() if v and k not in exclude}
            data['key'] = '/works/' + self.olid
            data['type'] = {'key': '/type/work'}
            if data.get('description'):
                data['description'] = {
                    'type': '/type/text',
                    'value': data['description'],
                }
            if data.get('notes'):
                data['notes'] = {'type': '/type/text', 'value': data['notes']}
            return data

        def validate(self) -> None:
            """Validates a Work's json representation against the canonical
            JSON Schema for Works using jsonschema.validate().
            Raises:
               jsonschema.exceptions.ValidationError if the Work is invalid.
            """
            return self.OL.validate(self, 'work.schema.json')

        @property
        def editions(self):
            """Returns a list of editions of related to a particular work
            Returns
                (List) of common.Edition books
            Usage:
                >>> from olclient import OpenLibrary
                >>> ol = OpenLibrary()
                >>> ol.Work(olid).editions
            """
            url = f'{self.OL.base_url}/works/{self.olid}/editions.json'
            r_json: Dict[Any, Any] = self.OL.session.get(url).json()
            editions: List[Any] = r_json.get('entries', [])

            while True:
                next_page_link: Optional[str] = r_json.get('links', {}).get('next')
                if next_page_link is not None:
                    r_json: Dict[Any, Any] = self.OL.session.get(
                        self.OL.base_url + next_page_link
                    ).json()
                    editions.extend(r_json.get('entries', []))
                else:
                    break

            self._editions = [
                self.OL.Edition(**self.OL.Edition.ol_edition_json_to_book_args(ed))
                for ed in editions
            ]
            return self._editions

        @classmethod
        def create(cls, book: Book, debug=False) -> Work:
            """Creates a new work along with a new edition
            Usage:
                >>> from olclient.openlibrary import OpenLibrary
                >>> import olclient.common as common
                >>> book = common.Book(title=u"Warlight: A novel", authors=[common.Author(name=u"Michael Ondaatje")], publisher=u"Deckle Edge", publish_date=u"2018")
                >>> book.add_id(u'isbn_10', u'0525521194')
                >>> book.add_id(u'isbn_13', u'978-0525521198'))
                >>> ol.Work.create(book)
            """
            year_matches_in_date: list[Any] = re.findall(r'[\d]{4}', book.publish_date)
            book.publish_date = year_matches_in_date[0] if len(year_matches_in_date) > 0 else ''
            ed = cls.OL.create_book(book, debug=debug)
            ed.add_bookcover(book.cover)
            work = ed.work
            work.add_bookcover(book.cover)
            return ed

        def add_author(self, author):
            author_role = {
                'type': {'key': '/type/author_role'},
                'author': {'key': '/authors/' + author.olid},
            }
            self.authors.append(author_role)
            return author_role

        def add_bookcover(self, url):
            return self.OL.session.post(
                f'{self.OL.base_url}/works/{self.olid}/-/add-cover',
                files={'file': '', 'url': url, 'upload': 'submit'},
            )

        def add_subject(self, subject, comment=''):
            return self.add_subjects([subject], comment)

        def add_subjects(self, subjects, comment=''):
            url = self.OL.base_url + "/works/" + self.olid + ".json"
            data = self.OL.session.get(url).json()
            original_subjects = data.get('subjects', [])
            changed_subjects = merge_unique_lists([original_subjects, subjects])
            data['_comment'] = comment or (
                f"adding {', '.join(subjects)} to subjects"
            )
            data['subjects'] = changed_subjects
            return self.OL.session.put(url, json.dumps(data))

        def rm_subjects(self, subjects, comment=''):
            url = self.OL.base_url + "/works/" + self.olid + ".json"
            r = self.OL.session.get(url)
            data = r.json()
            data['_comment'] = comment or (f"rm subjects: {', '.join(subjects)}")
            data['subjects'] = list(set(data['subjects']) - set(subjects))
            return self.OL.session.put(url, json.dumps(data))

        def delete(self, comment: str, confirm: bool = True) -> Optional[Response]:
            should_delete = confirm is False or get_approval_from_cli(
                f'Delete https://openlibrary.org/works/{self.olid} and its editions? (y/n)'
            )
            if should_delete is False:
                return None
            return self.OL.session.post(f'{self.OL.base_url}/works/{self.olid}/-/delete.json', params={'comment': comment})

        def save(self, comment):
            """Saves this work back to Open Library using the JSON API."""
            body = self.json()
            body['_comment'] = comment
            url = self.OL.base_url + f'/works/{self.olid}.json'
            return self.OL.session.put(url, json.dumps(body))

        @classmethod
        def get(cls, olid: str) -> Work:
            path = f'/works/{olid}.json'
            r = cls.OL.get_ol_response(path)
            return cls(olid, **r.json())

        @classmethod
        def search(cls, title: Optional[str] = None, author: Optional[str] = None) -> Optional[Book]:
            """Get the *closest* matching result in OpenLibrary based on a title
            and author.
            FIXME: This is essentially a Work and should be moved there
            Usage:
                >>> from olclient.openlibrary import OpenLibrary
                >>> ol = OpenLibrary()
                >>> ol.get_book_by_metadata(
                ...     title=u'The Autobiography of Benjamin Franklin')
                or
                >>> from olclient.openlibrary import OpenLibrary
                >>> ol = OpenLibrary()
                >>> ol.get_book_by_metadata(
                ...     author=u'Dan Brown')
            """
            if not (title or author):
                raise ValueError("Author or title required for metadata search")

            url = f'{cls.OL.base_url}/search.json?title={title}'
            if author:
                url += f'&author={author}'

            @backoff.on_exception(
                on_giveup=lambda error: logger.exception(
                    "Error retrieving metadata for book: %s", error
                ),
                **cls.OL.BACKOFF_KWARGS,
            )
            def _get_book_by_metadata(ol_url):
                return cls.OL.session.get(ol_url)

            response = _get_book_by_metadata(url)
            results = Results(**response.json())

            if results.num_found:
                return results.first.to_book()

            return None

    return Work
