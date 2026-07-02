"""
Integration tests for write/save operations.

These tests require a running OL instance with write credentials:

    OL_TEST_URL=http://localhost:8080 \
    OL_USERNAME=openlibrary@example.com \
    OL_PASSWORD=admin123 \
    pytest tests/integration/test_save.py -m integration -v

WARNING: These tests make real edits to the OL instance pointed at by
OL_TEST_URL. Only run against a local Docker instance, never against
openlibrary.org.
"""

import os

import pytest


def requires_write_auth(ol_local):
    """Skip if OL_USERNAME/OL_PASSWORD were not provided."""
    if not os.environ.get("OL_USERNAME"):
        pytest.skip("OL_USERNAME not set — write tests require auth")


@pytest.mark.integration
class TestEditionSave:
    def test_save_edition_title_change(self, ol_local):
        requires_write_auth(ol_local)

        e = ol_local.Edition.get('OL7353617M')
        assert e is not None

        original_title = e.title
        e.title = original_title + " (integration test)"
        e.save("integration test: title change")

        # Verify the change persisted
        e2 = ol_local.Edition.get('OL7353617M')
        assert e2.title == e.title

        # Restore original title
        e2.title = original_title
        e2.save("integration test: restore title")

        e3 = ol_local.Edition.get('OL7353617M')
        assert e3.title == original_title


@pytest.mark.integration
class TestWorkSave:
    def test_save_work_description_change(self, ol_local):
        requires_write_auth(ol_local)

        w = ol_local.Work.get('OL45804W')
        assert w is not None

        # Store original description (may be None)
        original_desc = getattr(w, 'description', None)
        w.description = "Integration test description — safe to revert."
        w.save("integration test: description change")

        # Verify
        w2 = ol_local.Work.get('OL45804W')
        assert w2.description == w.description

        # Restore
        w2.description = original_desc
        w2.save("integration test: restore description")
