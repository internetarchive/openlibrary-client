import json
from urllib.parse import urlencode

from olclient.common import Entity


def get_tag_helper_class(ol_context):
    class Tag(Entity):
        """Represents an Open Library Tag (/tags/OLnT).

        A Tag has a name, a tag_type (e.g. 'subject', 'genres'), an optional
        tag_description and optional body HTML.

        Usage:
            >>> tag = ol.Tag.get('OL32T')
            >>> print(tag.name, tag.tag_type)
            cooking subject
        """

        OL = ol_context

        def __init__(self, olid, name, tag_type='subject', identifiers=None, **kwargs):
            super().__init__(identifiers)
            self.olid = olid
            self.name = name
            self.tag_type = tag_type
            for key, value in kwargs.items():
                setattr(self, key, value)

        def json(self) -> dict:
            """Returns a dict JSON representation suitable for saving to OL."""
            data = {k: v for k, v in self.__dict__.items() if v and k != 'olid'}
            data['key'] = f'/tags/{self.olid}'
            data['type'] = {'key': '/type/tag'}
            return data

        def validate(self) -> None:
            """Validates against tag.schema.json. Raises on an invalid Tag."""
            return self.OL.validate(self, 'tag.schema.json')

        def save(self, comment):
            """Saves this Tag back to Open Library using the JSON API."""
            body = self.json()
            body['_comment'] = comment
            url = self.OL.base_url + f'/tags/{self.olid}.json'
            return self.OL.session.put(url, json.dumps(body))

        @classmethod
        def _from_doc(cls, data):
            """Builds a Tag from an OL document dict (consumes ``data``)."""
            olid = data.pop('key', '').split('/')[-1]
            name = data.pop('name', '')
            tag_type = data.pop('tag_type', 'subject')
            data.pop('type', None)
            return cls(olid, name=name, tag_type=tag_type, **data)

        @classmethod
        def get(cls, olid):
            """Retrieves a Tag by olid (e.g. 'OL32T'), or None if not found."""
            data = cls.OL.get_ol_response(f'/tags/{olid}.json').json()
            if 'error' in data:
                return None
            return cls._from_doc(data)

        @classmethod
        def find(cls, tag_type, name=None, limit=1000):
            """Returns every Tag of ``tag_type`` (optionally filtered by name).

            The name match is done in Python because ``query.json``'s
            ``name~=`` prefix match is case-sensitive.
            """
            query = urlencode(
                {'type': '/type/tag', 'tag_type': tag_type, '*': '', 'limit': limit}
            )
            docs = cls.OL.get_ol_response(f'/query.json?{query}').json()
            tags = [cls._from_doc(dict(doc)) for doc in docs]
            if name:
                needle = name.strip().casefold()
                tags = [t for t in tags if (t.name or '').strip().casefold() == needle]
            return tags

        @classmethod
        def create(cls, name, tag_type, description='', comment='add tag', slugs=None):
            """Creates a new Tag via ``POST /api/new`` and returns its key.

            Returns:
                str - the new Tag's key, e.g. '/tags/OL123T'.
            """
            doc = {'type': {'key': '/type/tag'}, 'name': name, 'tag_type': tag_type}
            if description:
                doc['tag_description'] = description
            if slugs:
                doc['slugs'] = slugs
            headers = {
                'Opt': '"http://openlibrary.org/dev/docs/api"; ns=42',
                '42-comment': comment,
            }
            url = cls.OL.base_url + '/api/new'
            r = cls.OL.session.post(url, json.dumps([doc]), headers=headers)
            r.raise_for_status()
            keys = r.json()
            if not keys:
                raise ValueError(f"/api/new returned no key: {r.text[:200]}")
            return keys[0]

    return Tag
