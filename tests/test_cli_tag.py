"""Tests for ``ol tag add`` (issue #458): AND-subject selection via /search.json,
the shared write engine, slug-based subject removal, and already-tagged no-ops.

No network, no credentials: a fake client answers /search.json and work fetches.
"""

import pytest

from olclient.cli import _works_matching_all_subjects, cmd_tag_add
from tests.conftest import FakeOL, FakeTag, make_tag_args


# --- selection query --------------------------------------------------------

def test_selection_ands_subject_keys_and_excludes_tag():
    ol = FakeOL(search_keys=["/works/OL1W"])
    keys = _works_matching_all_subjects(
        ol, ["graphic_design", "paintings"], tag_type="genre", tag_olid="OL1T", limit=5)
    assert keys == ["/works/OL1W"]
    q = ol.search_calls[0]
    assert "subject_key%3Agraphic_design" in q
    assert "subject_key%3Apaintings" in q
    assert "+AND+" in q
    assert "-genre_key%3AOL1T" in q  # exclude already-tagged


# --- end to end -------------------------------------------------------------

def test_dry_run_by_default_writes_nothing(patch_authed_ol, capsys):
    ol = patch_authed_ol(FakeOL(
        tags={"OL1T": FakeTag(name="Graphic Design", tag_type="genre")},
        search_keys=["/works/OL9W"],
        work_docs={"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": []}},
    ))
    cmd_tag_add(make_tag_args())
    assert ol.saved == []
    assert "DRY RUN" in capsys.readouterr().out


def test_approve_adds_tag_reference_to_the_right_field(patch_authed_ol, capsys):
    ol = patch_authed_ol(FakeOL(
        tags={"OL1T": FakeTag(name="Graphic Design", tag_type="genre")},
        search_keys=["/works/OL9W"],
        work_docs={"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": []}},
    ))
    cmd_tag_add(make_tag_args(approve=True))
    assert len(ol.saved) == 1
    (doc,) = ol.saved[0]
    assert doc["genres"] == [{"key": "/tags/OL1T"}]


def test_already_tagged_work_is_a_noop(patch_authed_ol, capsys):
    ol = patch_authed_ol(FakeOL(
        tags={"OL1T": FakeTag(name="Graphic Design", tag_type="genre")},
        search_keys=["/works/OL9W"],
        work_docs={"OL9W": {"key": "/works/OL9W", "revision": 3,
                            "genres": [{"key": "/tags/OL1T"}]}},
    ))
    cmd_tag_add(make_tag_args(approve=True))
    assert ol.saved == []  # nothing to write


def test_rm_subjects_removes_by_slug(patch_authed_ol, capsys):
    ol = patch_authed_ol(FakeOL(
        tags={"OL1T": FakeTag(name="Graphic Design", tag_type="genre")},
        search_keys=["/works/OL9W"],
        work_docs={"OL9W": {"key": "/works/OL9W", "revision": 3, "genres": [],
                            "subjects": ["Art, German", "Keep me"]}},
    ))
    cmd_tag_add(make_tag_args(rm_subjects="art_german", approve=True))
    (doc,) = ol.saved[0]
    assert doc["genres"] == [{"key": "/tags/OL1T"}]
    assert doc["subjects"] == ["Keep me"]  # 'Art, German' slug == art_german, dropped


def test_unknown_tag_aborts(patch_authed_ol):
    patch_authed_ol(FakeOL())
    with pytest.raises(SystemExit):
        cmd_tag_add(make_tag_args())
