"""
covers.py
~~~~~~~~~

Client-side cover image fetching.

Open Library's server side only fetches cover images itself from a small
allowlist of hosts (see ``openlibrary/coverstore/utils.py::ALLOWED_COVER_URLS``
and ``openlibrary/catalog/add_book/__init__.py::ALLOWED_COVER_HOSTS``) — a
``cover`` URL on any other host (most import-provider CDNs, e.g. bookdash.org)
is either silently dropped or rejected with a 400, and the image never gets
attached. ``fetch_cover_bytes()`` downloads the image from wherever
openlibrary-client happens to be running instead, so the caller can upload
the raw bytes the same way the site's paste-image upload UI does — a path
that never asks the OL server to fetch anything itself, so it isn't subject
to that allowlist.
"""

from __future__ import annotations

import logging
from typing import Tuple

import requests

logger = logging.getLogger('openlibrary')

# Mirrors openlibrary/plugins/upstream/covers.py image_validator.max_file_size
MAX_COVER_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT = 15
_ALLOWED_SCHEMES = ('http', 'https')
_KNOWN_EXTENSIONS = ('.jpg', '.jpeg', '.gif', '.png', '.webp')
# Mirrors openlibrary/plugins/upstream/covers.py image_validator.allowed_extensions
_CONTENT_TYPE_EXTENSIONS = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
}
_DEFAULT_EXTENSION = '.jpg'


class CoverFetchError(Exception):
    """A cover image could not be fetched or was unusable.

    Callers (import/edit flows) should catch this and skip the cover
    rather than fail the whole record — a bad or unreachable cover URL
    is never a reason to lose the rest of an import.
    """


def fetch_cover_bytes(
    url: str,
    *,
    max_bytes: int = MAX_COVER_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
) -> Tuple[bytes, str, str]:
    """Downloads the image at `url`.

    Returns (data, filename, content_type). Raises CoverFetchError for
    anything that should result in the cover being skipped: a missing URL,
    an unsupported URL scheme, a network/HTTP failure, a non-image response,
    or a file over `max_bytes` (deep image-content validation, e.g. corrupt
    image data, is left to the server's own image_validator on upload).
    """
    # `cover` is optional throughout the import pipeline (OLImportRecord.cover
    # is Optional[str], common.Book.cover defaults to ''), so a record with no
    # cover reaches us as None/'' — that's a skip, not a TypeError.
    if not url or not isinstance(url, str):
        raise CoverFetchError(f'no cover URL to fetch (got {url!r})')

    scheme = url.split('://', 1)[0].lower() if '://' in url else ''
    if scheme not in _ALLOWED_SCHEMES:
        raise CoverFetchError(f'unsupported URL scheme in {url!r}')

    try:
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise CoverFetchError(f'failed to fetch {url!r}: {e}') from e

    try:
        content_type = (
            response.headers.get('Content-Type', '').split(';')[0].strip().lower()
        )
        if not content_type.startswith('image/'):
            raise CoverFetchError(
                f'{url!r} is not an image (Content-Type: {content_type!r})'
            )

        content_length = response.headers.get('Content-Length')
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    raise CoverFetchError(
                        f'{url!r} exceeds {max_bytes}-byte limit '
                        f'(Content-Length: {content_length})'
                    )
            except ValueError:
                pass  # malformed header; fall through to the streamed cap below

        data = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise CoverFetchError(f'{url!r} exceeds {max_bytes}-byte limit')
    finally:
        response.close()

    if not data:
        raise CoverFetchError(f'{url!r} returned an empty response')

    filename = _filename_for(url, content_type)
    return bytes(data), filename, content_type


def upload_cover_from_url(cover_url, upload_bytes, *, olid=''):
    """Fetches `cover_url` client-side and hands the bytes to `upload_bytes`.

    `upload_bytes` is an entity's `add_book_cover_from_file(file_name,
    cover_data, mime_type)` — Edition's and Work's differ only in which
    endpoint they POST to, so the fetch-and-skip semantics live here once.

    Returns the upload's Response, or None if the cover could not be
    fetched or was not a usable image. A bad cover URL is never a reason
    to fail the rest of a record, so this never raises CoverFetchError.
    """
    try:
        cover_data, file_name, mime_type = fetch_cover_bytes(cover_url)
    except CoverFetchError as e:
        logger.warning('add_bookcover(%s): skipping cover %r — %s', olid, cover_url, e)
        return None
    return upload_bytes(file_name, cover_data, mime_type)


def _filename_for(url: str, content_type: str) -> str:
    """Best-effort filename with an extension the server's image_validator
    will accept. An unrecognized extension gets the whole upload rejected
    even when the bytes are a valid image, so prefer the Content-Type over
    trusting the URL if the URL's extension isn't one of the known ones.
    """
    path = url.split('?', 1)[0].split('#', 1)[0]
    name = path.rsplit('/', 1)[-1] or 'cover'
    base, _, ext = name.rpartition('.')
    if f'.{ext.lower()}' in _KNOWN_EXTENSIONS and base:
        return name
    extension = _CONTENT_TYPE_EXTENSIONS.get(content_type, _DEFAULT_EXTENSION)
    return f'{base or name}{extension}'
