"""Tests for ``ol subject`` — the merge winner logic plus the combined
merge + --add-tags flow (one write per work: add tags, remove the listed
subjects, add the canonical) and the selector scoping to the listed subjects.
"""

import pytest

from olclient.cli import _resolve_add_tags, cmd_subject, pick_winner
from tests.conftest import FakeOL, FakeTag, make_subject_args


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


def _steampunk_ol():
    return FakeOL(
        tags={
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


def test_merge_into_new_canonical_scopes_selector_to_listed_subjects(patch_authed_ol):
    ol = patch_authed_ol(_steampunk_ol())
    args = make_subject_args(merge=["Steampunk fiction", "steampunk fiction"],
                             into="Steampunk", approve=True)
    cmd_subject(args)
    # the new canonical "Steampunk" is NOT selected on — only the listed variants
    assert "Steampunk" not in ol.selected_subjects
    assert set(ol.selected_subjects) == {"Steampunk fiction", "steampunk fiction"}


def test_merge_with_add_tags_one_write_adds_tags_removes_subjects_adds_canonical(patch_authed_ol):
    ol = patch_authed_ol(_steampunk_ol())
    args = make_subject_args(
        merge=["Steampunk fiction"], into="Steampunk", approve=True,
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
    ol = FakeOL(tags_by_type_name={("genre", "nope"): []})
    with pytest.raises(SystemExit):
        _resolve_add_tags(ol, ["genre:Nope"])
    ol2 = FakeOL(tags_by_type_name={("genre", "dup"): [FakeTag("OLaT", "Dup", "genre"),
                                                       FakeTag("OLbT", "Dup", "genre")]})
    with pytest.raises(SystemExit):
        _resolve_add_tags(ol2, ["genre:Dup"])


def test_resolve_add_tags_passthrough_key():
    ol = FakeOL()
    assert _resolve_add_tags(ol, ["/tags/OL7T"]) == ["/tags/OL7T"]


# --- --select (datastore tag-by-subject, no removal) ------------------------

def test_select_tags_works_without_removing_subjects(patch_authed_ol):
    ol = patch_authed_ol(_steampunk_ol())
    args = make_subject_args(select=["Steampunk fiction"], add_tags=["literary_form:fiction"],
                             approve=True)
    cmd_subject(args)
    (doc,) = ol.saved[0]
    assert doc["literary_forms"] == [{"key": "/tags/OL2T"}]   # tag added
    assert "Steampunk fiction" in doc["subjects"]              # subject KEPT (no removal)


def test_select_dry_run_without_approve_writes_nothing(patch_authed_ol, capsys):
    ol = patch_authed_ol(_steampunk_ol())
    args = make_subject_args(select=["Steampunk fiction"], add_tags=["literary_form:fiction"],
                             approve=False)
    cmd_subject(args)
    assert ol.saved == []
    assert "DRY RUN" in capsys.readouterr().out


def test_select_requires_add_tags_or_add(patch_authed_ol):
    ol = patch_authed_ol(_steampunk_ol())
    with pytest.raises(SystemExit):
        cmd_subject(make_subject_args(select=["Steampunk fiction"]))


def test_select_skips_a_failing_subject_and_continues(patch_authed_ol):
    tag = FakeTag("OL2T", "Fiction", "literary_form")
    ol = patch_authed_ol(FakeOL(
        tags={"OL2T": tag},
        tags_by_type_name={("literary_form", "fiction"): [tag]},
        subject_works={"good": ["/works/OL1W"], "bad": ["/works/OL2W"]},
        work_docs={"OL1W": {"revision": 1}, "OL2W": {"revision": 1}},
    ))
    orig = ol.works_by_subject

    def flaky(subject, **kw):  # one subject's fetch fails mid-run
        if subject == "bad":
            raise ConnectionError("Connection reset by peer")
        yield from orig(subject, **kw)

    ol.works_by_subject = flaky
    cmd_subject(make_subject_args(select=["good", "bad"],
                                  add_tags=["literary_form:fiction"], approve=True))
    # 'good' was written, 'bad' was skipped, and the run did not crash
    written = [d["key"] for batch in ol.saved for d in batch]
    assert written == ["/works/OL1W"]


def _windowed_ol(n_works):
    tag = FakeTag("OL2T", "Fiction", "literary_form")
    keys = [f"/works/OL{i}W" for i in range(n_works)]
    return FakeOL(
        tags={"OL2T": tag},
        tags_by_type_name={("literary_form", "fiction"): [tag]},
        subject_works={"Big": keys},
        work_docs={f"OL{i}W": {"key": keys[i], "revision": 1} for i in range(n_works)},
    )


def test_select_window_writes_all_works_and_checkpoints(patch_authed_ol, tmp_path):
    ol = patch_authed_ol(_windowed_ol(5))
    progress = tmp_path / "big.progress"
    cmd_subject(make_subject_args(
        select=["Big"], add_tags=["literary_form:fiction"], approve=True,
        window=2, batch_size=100, progress_file=str(progress)))
    # every work got tagged, across windows of 2 (2 + 2 + 1)
    written = [d["key"] for batch in ol.saved for d in batch]
    assert written == [f"/works/OL{i}W" for i in range(5)]
    # progress holds per-window checkpoints plus a final bare "done" line
    lines = progress.read_text().splitlines()
    assert "Big\t2" in lines and "Big\t4" in lines and "Big\t5" in lines
    assert "Big" in lines  # fully-done sentinel


def test_select_window_resumes_from_checkpoint(patch_authed_ol, tmp_path):
    ol = patch_authed_ol(_windowed_ol(5))
    progress = tmp_path / "big.progress"
    progress.write_text("Big\t4\n")  # first 4 already done in a prior run
    cmd_subject(make_subject_args(
        select=["Big"], add_tags=["literary_form:fiction"], approve=True,
        window=2, batch_size=100, progress_file=str(progress)))
    # only the 5th work (offset 4) is examined/written on resume
    written = [d["key"] for batch in ol.saved for d in batch]
    assert written == ["/works/OL4W"]


def test_select_window_skips_fully_done_subject(patch_authed_ol, tmp_path):
    ol = patch_authed_ol(_windowed_ol(5))
    progress = tmp_path / "big.progress"
    progress.write_text("Big\n")  # bare line => fully done
    cmd_subject(make_subject_args(
        select=["Big"], add_tags=["literary_form:fiction"], approve=True,
        window=2, batch_size=100, progress_file=str(progress)))
    assert ol.saved == []  # nothing re-examined or re-written
