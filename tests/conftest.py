"""
Pytest fixtures and shared unit-test doubles.

Integration tests require a running OL instance (local Docker or staging).
They are skipped unless OL_TEST_URL is set:

    OL_TEST_URL=http://localhost:8080 pytest tests/integration/ -m integration

For write tests, also set:
    OL_USERNAME=openlibrary@example.com
    OL_PASSWORD=admin123

The ``Fake*`` doubles and the ``make_*_args`` helpers below are shared by the
unit tests for the ``ol`` CLI and the rule engine (``test_cli_tag``,
``test_cli_subject``, ``test_rule``). None of them touch the network.
"""

import json
import os
import types

import pytest

from olclient.openlibrary import OpenLibrary


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires a running OL instance (set OL_TEST_URL)",
    )


# --- shared unit-test doubles ----------------------------------------------


class FakeResponse:
    """A stand-in for a ``requests`` response carrying a JSON payload."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeTag:
    """A fake Tag object (``olid`` / ``name`` / ``tag_type``)."""

    def __init__(self, olid=None, name=None, tag_type=None):
        self.olid = olid
        self.name = name
        self.tag_type = tag_type


def tag(tag_type, name):
    """Convenience builder for a ``FakeTag`` by (tag_type, name)."""
    return FakeTag(name=name, tag_type=tag_type)


class FakeTagAPI:
    """Fake ``ol.Tag`` supporting ``.get(olid)`` and ``.find(tag_type, name)``."""

    def __init__(self, by_olid=None, by_type_name=None):
        self._by_olid = by_olid or {}
        self._by_type_name = by_type_name or {}

    def get(self, olid):
        return self._by_olid.get(olid)

    def find(self, tag_type, name=None):
        return list(self._by_type_name.get((tag_type, (name or "").casefold()), []))


class FakeOL:
    """A configurable fake OpenLibrary client.

    Answers ``/search.json`` (from ``search_keys``) and ``/works/<olid>.json``
    (from ``work_docs``), resolves tags by olid and by (type, name), selects
    works by subject, and records every ``save_many`` POST into ``.saved``.
    """

    def __init__(self, *, tags=None, tags_by_type_name=None, search_keys=None,
                 subject_works=None, subjects=None, work_docs=None,
                 user="/people/openlibrarytagsbot", post_status=200):
        self.Tag = FakeTagAPI(tags or {}, tags_by_type_name or {})
        self._search_keys = search_keys or []
        self._subject_works = subject_works or {}
        self._subjects = subjects or []
        self._work_docs = work_docs or {}
        self.post_status = post_status
        self.base_url = "https://openlibrary.org"
        self.search_calls = []
        self.selected_subjects = []
        self.saved = []
        cookies = types.SimpleNamespace(get=lambda name: user)
        self.session = types.SimpleNamespace(post=self._post, cookies=cookies)

    def search_subjects(self, q, limit=10, subject_type=None):
        return [h for h in self._subjects if h["name"].lower() == q.lower()]

    def works_by_subject(self, subject, subject_type="subject", limit=None):
        self.selected_subjects.append(subject)
        keys = self._subject_works.get(subject, [])
        yield from (keys if limit is None else keys[:limit])

    def get_ol_response(self, path):
        if path.startswith("/search.json"):
            self.search_calls.append(path)
            return FakeResponse({"docs": [{"key": k} for k in self._search_keys]})
        olid = path.rstrip("/").split("/")[-1].removesuffix(".json")
        return FakeResponse(self._work_docs[olid])

    def _post(self, url, data=None, headers=None):
        self.saved.append(json.loads(data))
        return types.SimpleNamespace(
            status_code=self.post_status, raise_for_status=lambda: None)


@pytest.fixture
def patch_authed_ol(monkeypatch):
    """Return ``install(ol)`` which points ``cli._authed_ol`` at ``ol``."""

    def install(ol):
        monkeypatch.setattr(
            "olclient.cli._authed_ol", lambda baseurl=None: ol)
        return ol

    return install


def make_tag_args(**over):
    """Arg namespace for ``ol tag add`` (``cmd_tag_add``)."""
    base = dict(
        baseurl=None, tag_olid="OL1T", subjects="graphic_design,paintings",
        rm_subjects=None, limit=100, batch_size=250, comment="tag works by subject",
        audit=None, show_payload=False, as_account="openlibrarytagsbot", approve=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def make_subject_args(**over):
    """Arg namespace for ``ol subject`` (``cmd_subject``)."""
    base = dict(
        baseurl=None, merge=None, into=None, remove=None, add=None, add_tags=None,
        select=None, select_file=None, progress_file=None,
        type="subject", limit=50, batch_size=250, comment="merge/clean subjects",
        audit=None, dry_run=False, show_payload=False,
        as_account="openlibrarytagsbot", approve=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


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
