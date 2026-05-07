"""
Tests for OpenLibrary.submit_batch() and OpenLibrary.get_batch().

All HTTP calls are mocked — no network required.
"""

from unittest.mock import MagicMock, patch

import pytest

from olclient.imports import OLAuthor, OLImportRecord
from olclient.openlibrary import OpenLibrary


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_RECORD = OLImportRecord(
    title="Test Book",
    source_records=["itan_technologies:BOO0001"],
    authors=[OLAuthor(name="Author One")],
    publishers=["Test Press"],
    publish_date="2024",
)

SUCCESS_HTML = """
<p>Import results for batch: Batch #42 (batch-abc123def456)</p>
<p>Records submitted: 3</p>
<p>Total queued: 3</p>
<p>Total skipped: 0</p>
<a href="/import/batch/42">View Batch Status</a>
"""

ERROR_HTML = """
<p>Import failed.</p>
<p>No import will be queued until *every* record validates successfully.</p>
<p>Validation errors:</p>
<li><strong>Line 2:</strong> Publication year too old</li>
<li><strong>Line 3:</strong> Source needs ISBN</li>
"""

BATCH_STATUS_HTML = """
<p>Batch ID: 42</p>
<p>Batch Name: batch-abc123def456</p>
<p>Submitter: mek</p>
<p>Submit Time: 2026-05-07 00:30:00</p>
<h2>Status Summary</h2>
<ul>
    <li>pending: 52</li>
    <li>needs_review: 10</li>
    <li>imported: 5</li>
    <li>error: 0</li>
</ul>
"""


@pytest.fixture
def ol():
    with patch('olclient.openlibrary.OpenLibrary.login'):
        client = OpenLibrary()
        client.base_url = 'https://openlibrary.org'
        return client


def _mock_response(status_code=200, text=''):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# submit_batch — dry_run
# ---------------------------------------------------------------------------

class TestSubmitBatchDryRun:
    def test_dry_run_returns_count_no_http(self, ol):
        ol.session.post = MagicMock()
        result = ol.submit_batch([MINIMAL_RECORD, MINIMAL_RECORD], dry_run=True)
        assert result == {'dry_run': True, 'record_count': 2}
        ol.session.post.assert_not_called()

    def test_dry_run_accepts_dicts(self, ol):
        raw = {'title': 'X', 'source_records': ['test:1'], 'authors': [{'name': 'A'}],
                'publishers': ['P'], 'publish_date': '2024'}
        ol.session.post = MagicMock()
        result = ol.submit_batch([raw], dry_run=True)
        assert result['record_count'] == 1

    def test_dry_run_empty_records(self, ol):
        ol.session.post = MagicMock()
        result = ol.submit_batch([], dry_run=True)
        assert result['record_count'] == 0


# ---------------------------------------------------------------------------
# submit_batch — success
# ---------------------------------------------------------------------------

class TestSubmitBatchSuccess:
    def test_success_parses_batch_id(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['success'] is True
        assert result['batch_id'] == 42

    def test_success_parses_batch_name(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['batch_name'] == 'batch-abc123def456'

    def test_success_parses_counts(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['total_submitted'] == 3
        assert result['total_queued'] == 3
        assert result['total_skipped'] == 0

    def test_success_builds_batch_url(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['batch_url'] == 'https://openlibrary.org/import/batch/42'

    def test_posts_to_correct_endpoint(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        ol.submit_batch([MINIMAL_RECORD])
        call_url = ol.session.post.call_args[0][0]
        assert call_url == 'https://openlibrary.org/import/batch/new'

    def test_posts_jsonl_as_form_field(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        ol.submit_batch([MINIMAL_RECORD])
        form_data = ol.session.post.call_args[1]['data']
        assert 'batchImportText' in form_data
        # Each line should be valid JSON
        import json
        for line in form_data['batchImportText'].strip().splitlines():
            parsed = json.loads(line)
            assert parsed['title'] == 'Test Book'

    def test_ol_import_record_serialized_without_none(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, SUCCESS_HTML))
        ol.submit_batch([MINIMAL_RECORD])
        import json
        form_data = ol.session.post.call_args[1]['data']
        parsed = json.loads(form_data['batchImportText'])
        assert 'subtitle' not in parsed  # excluded because None


# ---------------------------------------------------------------------------
# submit_batch — errors
# ---------------------------------------------------------------------------

class TestSubmitBatchErrors:
    def test_validation_errors_returned(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, ERROR_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['success'] is False
        assert len(result['errors']) == 2

    def test_error_line_numbers_parsed(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, ERROR_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['errors'][0]['line'] == 2
        assert result['errors'][1]['line'] == 3

    def test_error_messages_parsed(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, ERROR_HTML))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert 'Publication year too old' in result['errors'][0]['message']
        assert 'Source needs ISBN' in result['errors'][1]['message']

    def test_403_raises_permission_error(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(403, 'Forbidden'))
        with pytest.raises(PermissionError):
            ol.submit_batch([MINIMAL_RECORD])

    def test_unexpected_response_returns_failure(self, ol):
        ol.session.post = MagicMock(return_value=_mock_response(200, '<html>Something went wrong</html>'))
        result = ol.submit_batch([MINIMAL_RECORD])
        assert result['success'] is False
        assert result['errors'][0]['line'] == 0


# ---------------------------------------------------------------------------
# get_batch
# ---------------------------------------------------------------------------

class TestGetBatch:
    def test_returns_batch_id(self, ol):
        ol.session.get = MagicMock(return_value=_mock_response(200, BATCH_STATUS_HTML))
        result = ol.get_batch(42)
        assert result['batch_id'] == 42

    def test_returns_status_counts(self, ol):
        ol.session.get = MagicMock(return_value=_mock_response(200, BATCH_STATUS_HTML))
        result = ol.get_batch(42)
        assert result['status_counts']['pending'] == 52
        assert result['status_counts']['needs_review'] == 10
        assert result['status_counts']['imported'] == 5
        assert result['status_counts']['error'] == 0

    def test_returns_batch_url(self, ol):
        ol.session.get = MagicMock(return_value=_mock_response(200, BATCH_STATUS_HTML))
        result = ol.get_batch(42)
        assert result['batch_url'] == 'https://openlibrary.org/import/batch/42'

    def test_gets_correct_endpoint(self, ol):
        ol.session.get = MagicMock(return_value=_mock_response(200, BATCH_STATUS_HTML))
        ol.get_batch(42)
        ol.session.get.assert_called_once_with('https://openlibrary.org/import/batch/42')

    def test_404_raises_value_error(self, ol):
        ol.session.get = MagicMock(return_value=_mock_response(404, 'Not Found'))
        with pytest.raises(ValueError, match="not found"):
            ol.get_batch(99999)

    def test_403_raises_permission_error(self, ol):
        ol.session.get = MagicMock(return_value=_mock_response(403, 'Forbidden'))
        with pytest.raises(PermissionError):
            ol.get_batch(42)
