"""Tests for ``ol tag add`` (issue #458): AND-subject selection via /search.json,
the shared write engine, slug-based subject removal, and already-tagged no-ops.

No network, no credentials: a fake client answers /search.json and work fetches.
"""

import json
import types

import pytest

from olclient import cli
from olclient.cli import _works_matching_all_subjects, cmd_tag_add


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeTag:
    def __init__(self, name, tag_type):
        self.name = name
        self.tag_type = tag_type


class FakeTagAPI:
    def __init__(self, tags):
        self._tags = tags

    def get(self, olid):
        return self._tags.get(olid)


class FakeOL:
    """Answers /search.json (returns ``search_keys``) and /works/<olid>.json."""

    def __init__(self, tags, search_keys, work_docs, user="/people/openlibrarytagsbot"):
        self.Tag = FakeTagAPI(tags)
        self._search_keys = search_keys
        self._work_docs = work_docs
        self.base_url = "https://openlibrary.org"
        self.search_calls = []
        self.saved = []
        cookies = types.SimpleNamespace(get=lambda name: user)
        self.session = types.SimpleNamespace(post=self._post, cookies=cookies)

    def get_ol_response(self, path):
        if path.startswith("/search.json"):
            self.search_calls.append(path)
            return FakeResponse({"docs": [{"key": k} for k in self._search_keys]})
        olid = path.rstrip("/").split("/")[-1].removesuffix(".json")
        return FakeResponse(self._work_docs[olid])

    def _post(self, url, data=None, headers=None):
        self.saved.append(json.loads(data))
        return types.SimpleNamespace(status_code=200, raise_for_status=lambda: None)


def _args(**over):
    base = dict(
        baseurl=None, tag_olid="OL1T", subjects="graphic_design,paintings",
        rm_subjects=None, limit=100, batch_size=250, comment="tag works by subject",
        audit=None, show_payload=False, as_account="openlibrarytagsbot", approve=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def _patch_ol(monkeypatch, ol):
    monkeypatch.setattr(cli, "_authed_ol", lambda baseurl=None: ol)


# --- selection query --------------------------------------------------------

def test_selection_ands_subject_keys_and_excludes_tag():
    ol = FakeOL({}, ["/works/OL1W"], {})
    keys = _works_matching_all_subjects(
        ol, ["graphic_design", "paintings"], tag_type="genre", tag_olid="OL1T", limit=5)
    assert keys == ["/works/OL1W"]
    q = ol.search_calls[0]
    assert "subject_key%3Agraphic_design" in q
    assert "subject_key%3Apaintings" in q
    assert "+AND+" in q
    assert "-genre_key%3AOL1T" in q  # exclude already-tagged


# --- end to end -------------------------------------------------------------

def test_dry_run_by_default_writes_nothing(monkeypatch, capsys):
    ol = FakeOL(
        {"OL1T": FakeTag("Graphic Design", "genre")},
        ["/works/OL9W"],
        {"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": []}},
    )
    _patch_ol(monkeypatch, ol)
    cmd_tag_add(_args())
    assert ol.saved == []
    assert "DRY RUN" in capsys.readouterr().out


def test_approve_adds_tag_reference_to_the_right_field(monkeypatch, capsys):
    ol = FakeOL(
        {"OL1T": FakeTag("Graphic Design", "genre")},
        ["/works/OL9W"],
        {"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": []}},
    )
    _patch_ol(monkeypatch, ol)
    cmd_tag_add(_args(approve=True))
    assert len(ol.saved) == 1
    (doc,) = ol.saved[0]
    assert doc["genres"] == [{"key": "/tags/OL1T"}]


def test_already_tagged_work_is_a_noop(monkeypatch, capsys):
    ol = FakeOL(
        {"OL1T": FakeTag("Graphic Design", "genre")},
        ["/works/OL9W"],
        {"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": [{"key": "/tags/OL1T"}]}},
    )
    _patch_ol(monkeypatch, ol)
    cmd_tag_add(_args(approve=True))
    assert ol.saved == []  # nothing to write


def test_rm_subjects_removes_by_slug(monkeypatch, capsys):
    ol = FakeOL(
        {"OL1T": FakeTag("Graphic Design", "genre")},
        ["/works/OL9W"],
        {"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": [],
                  "subjects": ["Art, German", "Keep me"]}},
    )
    _patch_ol(monkeypatch, ol)
    cmd_tag_add(_args(rm_subjects="art_german", approve=True))
    (doc,) = ol.saved[0]
    assert doc["genres"] == [{"key": "/tags/OL1T"}]
    assert doc["subjects"] == ["Keep me"]  # 'Art, German' slug == art_german, dropped


def test_unknown_tag_aborts(monkeypatch):
    ol = FakeOL({}, [], {})
    _patch_ol(monkeypatch, ol)
    with pytest.raises(SystemExit):
        cmd_tag_add(_args())
