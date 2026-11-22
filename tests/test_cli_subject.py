"""Tests for ``ol subject`` — the merge winner logic plus the combined
merge + --add-tags flow (one write per work: add tags, remove the listed
subjects, add the canonical) and the selector scoping to the listed subjects.
"""

import json
import types

import pytest

from olclient import cli
from olclient.cli import _resolve_add_tags, cmd_subject, pick_winner


def test_pick_winner_defaults_to_highest_count():
    counts = {"World War, 1939-1945": 5339, "World war, 1939-1945": 51}
    assert pick_winner(counts.get, list(counts)) == "World War, 1939-1945"


def test_into_overrides_counts():
    counts = {"A": 10, "B": 3}
    # --into forces a survivor, even one not among the variants
    assert pick_winner(counts.get, ["A", "B"], into="Canonical") == "Canonical"


def test_missing_counts_treated_as_zero():
    # unknown variant -> count None -> 0, never crashes
    assert pick_winner({"A": 2}.get, ["A", "B"]) == "A"


# --- combined merge + --add-tags -------------------------------------------

class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeTag:
    def __init__(self, olid, name, tag_type):
        self.olid = olid
        self.name = name
        self.tag_type = tag_type


class FakeTagAPI:
    def __init__(self, by_olid, by_type_name):
        self._by_olid = by_olid
        self._by_type_name = by_type_name

    def get(self, olid):
        return self._by_olid.get(olid)

    def find(self, tag_type, name=None):
        return list(self._by_type_name.get((tag_type, (name or "").casefold()), []))


class FakeOL:
    def __init__(self, tags_by_olid, tags_by_type_name, subject_works, work_docs,
                 user="/people/openlibrarytagsbot"):
        self.Tag = FakeTagAPI(tags_by_olid, tags_by_type_name)
        self._subject_works = subject_works
        self._work_docs = work_docs
        self.base_url = "https://openlibrary.org"
        self.selected_subjects = []
        self.saved = []
        cookies = types.SimpleNamespace(get=lambda name: user)
        self.session = types.SimpleNamespace(post=self._post, cookies=cookies)

    def search_subjects(self, q, limit=10, subject_type=None):
        return []

    def works_by_subject(self, subject, subject_type="subject", limit=None):
        self.selected_subjects.append(subject)
        keys = self._subject_works.get(subject, [])
        yield from (keys if limit is None else keys[:limit])

    def get_ol_response(self, path):
        olid = path.rstrip("/").split("/")[-1].removesuffix(".json")
        return FakeResponse(self._work_docs[olid])

    def _post(self, url, data=None, headers=None):
        self.saved.append(json.loads(data))
        return types.SimpleNamespace(status_code=200, raise_for_status=lambda: None)


def _subject_args(**over):
    base = dict(
        baseurl=None, merge=None, into=None, remove=None, add=None, add_tags=None,
        type="subject", limit=50, batch_size=250, comment="merge/clean subjects",
        audit=None, dry_run=False, show_payload=False,
        as_account="openlibrarytagsbot", yes=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def _steampunk_ol():
    return FakeOL(
        tags_by_olid={
            "OL1T": FakeTag("OL1T", "Steampunk", "subgenre"),
            "OL2T": FakeTag("OL2T", "Fiction", "literary_form"),
            "OL3T": FakeTag("OL3T", "Science Fiction", "genre"),
        },
        tags_by_type_name={
            ("subgenre", "steampunk"): [FakeTag("OL1T", "Steampunk", "subgenre")],
            ("literary_form", "fiction"): [FakeTag("OL2T", "Fiction", "literary_form")],
            ("genre", "science fiction"): [FakeTag("OL3T", "Science Fiction", "genre")],
        },
        subject_works={"Steampunk fiction": ["/works/OL9W"]},
        work_docs={"OL9W": {"key": "/works/OL9W", "revision": 2,
                            "subjects": ["Steampunk fiction", "Other"]}},
    )


def test_merge_into_new_canonical_scopes_selector_to_listed_subjects(monkeypatch):
    ol = _steampunk_ol()
    monkeypatch.setattr(cli, "_authed_ol", lambda baseurl=None: ol)
    args = _subject_args(merge=["Steampunk fiction", "steampunk fiction"], into="Steampunk",
                         yes=True)
    cmd_subject(args)
    # the new canonical "Steampunk" is NOT selected on — only the listed variants
    assert "Steampunk" not in ol.selected_subjects
    assert set(ol.selected_subjects) == {"Steampunk fiction", "steampunk fiction"}


def test_merge_with_add_tags_one_write_adds_tags_removes_subjects_adds_canonical(monkeypatch):
    ol = _steampunk_ol()
    monkeypatch.setattr(cli, "_authed_ol", lambda baseurl=None: ol)
    args = _subject_args(
        merge=["Steampunk fiction"], into="Steampunk", yes=True,
        add_tags=["subgenre:steampunk", "literary_form:fiction", "genre:Science Fiction"],
    )
    cmd_subject(args)
    assert len(ol.saved) == 1  # one save_many batch
    (doc,) = ol.saved[0]       # one work doc in it
    # all three changes in a single write:
    assert doc["subgenres"] == [{"key": "/tags/OL1T"}]
    assert doc["literary_forms"] == [{"key": "/tags/OL2T"}]
    assert doc["genres"] == [{"key": "/tags/OL3T"}]
    assert "Steampunk fiction" not in doc["subjects"]  # removed
    assert "Steampunk" in doc["subjects"]              # canonical added
    assert "Other" in doc["subjects"]                  # untouched


def test_resolve_add_tags_errors_on_missing_and_ambiguous():
    ol = FakeOL({}, {("genre", "nope"): []}, {}, {})
    with pytest.raises(SystemExit):
        _resolve_add_tags(ol, ["genre:Nope"])
    ol2 = FakeOL({}, {("genre", "dup"): [FakeTag("OLaT", "Dup", "genre"),
                                         FakeTag("OLbT", "Dup", "genre")]}, {}, {})
    with pytest.raises(SystemExit):
        _resolve_add_tags(ol2, ["genre:Dup"])


def test_resolve_add_tags_passthrough_key():
    ol = FakeOL({}, {}, {}, {})
    assert _resolve_add_tags(ol, ["/tags/OL7T"]) == ["/tags/OL7T"]
