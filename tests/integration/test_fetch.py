"""
Integration tests for read/fetch operations.

These tests require a running OL instance. Run with:

    OL_TEST_URL=http://localhost:8080 pytest tests/integration/test_fetch.py -m integration -v

Known-stable OL entities used below (from openlibrary.org production):
  - Work:    OL45804W   (Harry Potter and the Philosopher's Stone)
  - Edition: OL7353617M (same work, English edition)
  - Author:  OL23919A   (J. K. Rowling)
"""

import pytest


@pytest.mark.integration
class TestWorkFetch:
    def test_get_work_by_olid(self, ol_local):
        w = ol_local.Work.get('OL45804W')
        assert w is not None
        assert w.olid == 'OL45804W'
        assert w.title

    def test_get_work_has_authors(self, ol_local):
        w = ol_local.Work.get('OL45804W')
        assert isinstance(w.authors, list)

    def test_get_nonexistent_work_returns_none(self, ol_local):
        w = ol_local.Work.get('OL9999999999W')
        assert w is None


@pytest.mark.integration
class TestEditionFetch:
    def test_get_edition_by_olid(self, ol_local):
        e = ol_local.Edition.get('OL7353617M')
        assert e is not None
        assert e.olid == 'OL7353617M'
        assert e.title

    def test_get_edition_by_isbn(self, ol_local):
        e = ol_local.Edition.get(isbn='9780439708180')
        assert e is not None
        assert e.title

    def test_get_nonexistent_edition_returns_none(self, ol_local):
        e = ol_local.Edition.get('OL9999999999M')
        assert e is None


@pytest.mark.integration
class TestAuthorFetch:
    def test_get_author_by_olid(self, ol_local):
        a = ol_local.Author.get('OL23919A')
        assert a is not None
        assert a.olid == 'OL23919A'
        assert a.name

    def test_get_nonexistent_author_returns_none(self, ol_local):
        a = ol_local.Author.get('OL9999999999A')
        assert a is None


@pytest.mark.integration
class TestGenericGet:
    def test_get_dispatches_to_work(self, ol_local):
        result = ol_local.get('OL45804W')
        assert result is not None
        assert result.olid == 'OL45804W'

    def test_get_dispatches_to_edition(self, ol_local):
        result = ol_local.get('OL7353617M')
        assert result is not None
        assert result.olid == 'OL7353617M'

    def test_get_dispatches_to_author(self, ol_local):
        result = ol_local.get('OL23919A')
        assert result is not None
        assert result.olid == 'OL23919A'


@pytest.mark.integration
class TestBulkFetch:
    """Tests for get_many() — requires PR #440 to be merged."""

    def test_get_many_mixed_types(self, ol_local):
        if not hasattr(ol_local, 'get_many'):
            pytest.skip("get_many() not available (requires PR #440)")
        results = ol_local.get_many(['OL45804W', 'OL7353617M', 'OL23919A'])
        assert len(results) == 3

    def test_get_many_skips_missing(self, ol_local):
        if not hasattr(ol_local, 'get_many'):
            pytest.skip("get_many() not available (requires PR #440)")
        results = ol_local.get_many(['OL45804W', 'OL9999999999W'])
        assert len(results) == 1
        assert results[0].olid == 'OL45804W'

    def test_get_many_by_isbn(self, ol_local):
        if not hasattr(ol_local, 'get_many_by_isbn'):
            pytest.skip("get_many_by_isbn() not available (requires PR #440)")
        results = ol_local.get_many_by_isbn(['9780439708180'])
        assert len(results) >= 1
        assert results[0].title
