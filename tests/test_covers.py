"""Test cases for olclient.covers"""

from unittest.mock import Mock, patch

import pytest
import requests

from olclient.covers import CoverFetchError, fetch_cover_bytes


def make_response(content_type='image/jpeg', content_length=None, chunks=(b'abc',)):
    response = Mock()
    headers = {'Content-Type': content_type}
    if content_length is not None:
        headers['Content-Length'] = str(content_length)
    response.headers = headers
    response.raise_for_status = Mock()
    response.iter_content = Mock(return_value=iter(chunks))
    return response


class TestFetchCoverBytes:
    @patch('olclient.covers.requests.get')
    def test_success(self, mock_get):
        mock_get.return_value = make_response(chunks=(b'\xff\xd8\xff', b'restofjpeg'))

        data, filename, content_type = fetch_cover_bytes(
            'https://bookdash.org/wp-content/uploads/cover.jpg'
        )

        self.assert_fetched_ok(data, filename, content_type)

    def assert_fetched_ok(self, data, filename, content_type):
        assert data == b'\xff\xd8\xffrestofjpeg'
        assert filename == 'cover.jpg'
        assert content_type == 'image/jpeg'

    @pytest.mark.parametrize('url', [None, '', 0, []])
    @patch('olclient.covers.requests.get')
    def test_missing_url_raises_cover_fetch_error(self, mock_get, url):
        """A record with no cover must raise CoverFetchError (which callers
        skip on), not a TypeError that escapes the caller's except clause.
        """
        with pytest.raises(CoverFetchError):
            fetch_cover_bytes(url)
        mock_get.assert_not_called()

    @pytest.mark.parametrize('url', ['ftp://example.com/cover.jpg', 'not-a-url', ''])
    @patch('olclient.covers.requests.get')
    def test_rejects_unsupported_scheme_without_network_call(self, mock_get, url):
        with pytest.raises(CoverFetchError):
            fetch_cover_bytes(url)
        mock_get.assert_not_called()

    @patch('olclient.covers.requests.get')
    def test_network_failure_raises_cover_fetch_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError('nope')

        with pytest.raises(CoverFetchError):
            fetch_cover_bytes('https://bookdash.org/cover.jpg')

    @patch('olclient.covers.requests.get')
    def test_http_error_raises_cover_fetch_error(self, mock_get):
        response = make_response()
        response.raise_for_status.side_effect = requests.HTTPError('404')
        mock_get.return_value = response

        with pytest.raises(CoverFetchError):
            fetch_cover_bytes('https://bookdash.org/missing.jpg')

    @patch('olclient.covers.requests.get')
    def test_non_image_content_type_raises_cover_fetch_error(self, mock_get):
        mock_get.return_value = make_response(content_type='text/html')

        with pytest.raises(CoverFetchError):
            fetch_cover_bytes('https://bookdash.org/not-a-cover')

    @patch('olclient.covers.requests.get')
    def test_oversized_content_length_raises_before_reading_body(self, mock_get):
        response = make_response(content_length=100)
        mock_get.return_value = response

        with pytest.raises(CoverFetchError):
            fetch_cover_bytes('https://bookdash.org/huge.jpg', max_bytes=10)

        response.iter_content.assert_not_called()

    @patch('olclient.covers.requests.get')
    def test_oversized_streamed_body_raises_even_without_content_length(self, mock_get):
        mock_get.return_value = make_response(
            content_length=None, chunks=(b'0123456789', b'0123456789')
        )

        with pytest.raises(CoverFetchError):
            fetch_cover_bytes('https://bookdash.org/huge.jpg', max_bytes=10)

    @patch('olclient.covers.requests.get')
    def test_empty_response_raises_cover_fetch_error(self, mock_get):
        mock_get.return_value = make_response(chunks=())

        with pytest.raises(CoverFetchError):
            fetch_cover_bytes('https://bookdash.org/empty.jpg')

    @patch('olclient.covers.requests.get')
    def test_filename_falls_back_to_content_type_when_url_has_no_known_extension(
        self, mock_get
    ):
        mock_get.return_value = make_response(content_type='image/png')

        _, filename, _ = fetch_cover_bytes(
            'https://bookdash.org/wp-content/uploads/cover?size=large'
        )

        assert filename.endswith('.png')

    @patch('olclient.covers.requests.get')
    def test_filename_preserves_known_extension_from_url(self, mock_get):
        mock_get.return_value = make_response(content_type='image/jpeg')

        _, filename, _ = fetch_cover_bytes('https://bookdash.org/cover.png')

        assert filename == 'cover.png'
