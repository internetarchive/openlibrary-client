"""
Pytest fixtures for integration tests.

Integration tests require a running OL instance (local Docker or staging).
They are skipped unless OL_TEST_URL is set:

    OL_TEST_URL=http://localhost:8080 pytest tests/integration/ -m integration

For write tests, also set:
    OL_USERNAME=openlibrary@example.com
    OL_PASSWORD=admin123
"""

import os

import pytest

from olclient.openlibrary import OpenLibrary


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires a running OL instance (set OL_TEST_URL)",
    )


@pytest.fixture(scope="session")
def ol_local():
    """Return an OpenLibrary client pointed at OL_TEST_URL.

    Skips the test if OL_TEST_URL is not set. Logs in if OL_USERNAME
    and OL_PASSWORD are also set.
    """
    url = os.environ.get("OL_TEST_URL")
    if not url:
        pytest.skip("OL_TEST_URL not set — skipping integration tests")

    ol = OpenLibrary(base_url=url)

    username = os.environ.get("OL_USERNAME")
    password = os.environ.get("OL_PASSWORD")
    if username and password:
        from olclient.config import Credentials

        ol.login(Credentials(username, password))

    return ol
