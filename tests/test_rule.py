"""Tests for the rule engine (tags/rule.py), driven through a fake olclient.

No network and no credentials. Covers tag ref resolution (<tag_type>:<slug>), YAML
rule loading with per-subject keep/remove flags, multiple subjects (union), multiple
tags (mixed fields), add-only idempotent merge, subject removal, the authoritative
counts, no-op detection, dry-run safety, the identity guard, and the raw-dict save docs.
"""

import json
import types

import pytest

from olclient.rule import (
    Rule,
    apply_rule,
    build_save_docs,
    load_rule,
    logged_in_user,
    pack_batches,
    plan_rule,
    resolve_tag_ref,
    resolve_tags,
    save_many_request,
)
from tests.conftest import FakeOL, tag


def test_pack_batches_splits_by_count():
    docs = [{"k": i} for i in range(5)]  # 1 leaf each
    batches = list(pack_batches(docs, max_count=2, arg_budget=1000))
    assert [len(b) for b in batches] == [2, 2, 1]


def test_pack_batches_splits_by_arg_budget_before_count():
    # each doc ~4 leaves; a budget of 10 forces a split at 2 docs even though
    # max_count is 100
    docs = [{"a": 1, "b": 2, "c": 3, "d": 4} for _ in range(5)]
    batches = list(pack_batches(docs, max_count=100, arg_budget=10))
    assert all(sum(len(d) for d in b) <= 10 or len(b) == 1 for b in batches)
    assert [len(b) for b in batches] == [2, 2, 1]


def test_pack_batches_yields_oversized_lone_doc():
    big = {"xs": list(range(50))}  # 50 leaves, over budget
    batches = list(pack_batches([big], max_count=100, arg_budget=10))
    assert batches == [[big]]  # can't split a single doc


def test_save_with_split_retries_halves_on_460():
    from olclient.rule import _save_with_split

    class Resp:
        def __init__(self, status):
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError(f"unexpected raise on {self.status_code}")

    posts = []

    def post(url, data, headers=None):
        docs = json.loads(data)
        posts.append(len(docs))
        # WAF denies any batch with >1 doc; singletons go through
        return Resp(460 if len(docs) > 1 else 200)

    ol = types.SimpleNamespace(
        base_url="https://openlibrary.org",
        session=types.SimpleNamespace(post=post),
    )
    accepted = []
    docs = [{"key": f"/works/OL{i}W"} for i in range(4)]
    _save_with_split(ol, docs, "c", on_accept=lambda ds: accepted.extend(ds))
    # 4 -> 460, 2 -> 460, 2 -> 460, then four singletons succeed
    assert sum(1 for n in posts if n == 1) == 4
    assert [d["key"] for d in accepted] == [d["key"] for d in docs]


def test_save_with_split_single_doc_460_raises():
    from olclient.rule import _save_with_split

    class Resp:
        status_code = 460

        def raise_for_status(self):
            raise RuntimeError("460")

    ol = types.SimpleNamespace(
        base_url="https://openlibrary.org",
        session=types.SimpleNamespace(post=lambda *a, **k: Resp()),
    )
    with pytest.raises(RuntimeError):
        _save_with_split(ol, [{"key": "/works/OL1W"}], "c", on_accept=lambda ds: None)


NONFIC = tag("literary_form", "Nonfiction")
FICTION = tag("literary_form", "Fiction")
FANTASY = tag("genre", "Fantasy")

HITS = [
    {"name": "Nonfiction", "subject_type": "subject", "work_count": 38920},
    {"name": "Non-fiction", "subject_type": "subject", "work_count": 1200},
    {"name": "Fiction - Fantasy", "subject_type": "subject", "work_count": 534},
]


# A slug_to_tag_key stand-in: (vocab_dir, slug) -> key.
FAKE_VOCAB = {
    ("literary_form", "fiction"): "/tags/OL183T",
    ("genres", "fantasy"): "/tags/OL169T",
}


def fake_slug_to_tag_key(vocab_dir, slug):
    return FAKE_VOCAB.get((vocab_dir, slug))


# --- tag ref resolution -----------------------------------------------------


@pytest.mark.parametrize(
    "ref, expected",
    [
        # literary_form resolves from the singular dir ...
        ("literary_form:fiction", "/tags/OL183T"),
        # ... genre from the plural dir ...
        ("genre:fantasy", "/tags/OL169T"),
        # ... and a bare /tags/ key passes through untouched.
        ("/tags/OL184T", "/tags/OL184T"),
    ],
)
def test_resolve_tag_ref_resolves_or_passes_through(ref, expected):
    assert resolve_tag_ref(ref, fake_slug_to_tag_key) == expected


def test_resolve_tag_ref_unknown_raises():
    with pytest.raises(ValueError, match="no Tag found"):
        resolve_tag_ref("genre:nope", fake_slug_to_tag_key)


# --- YAML loading -----------------------------------------------------------


def test_load_rule_parses_keep_remove_and_tags(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "rule: fiction-fantasy\n"
        "subjects:\n"
        "  - ['Fiction - Fantasy', 0]\n"
        "  - ['Fantasy fiction', 1]\n"
        "tags:\n"
        "  - literary_form:fiction\n"
        "  - genre:fantasy\n"
    )
    rule = load_rule(str(p), fake_slug_to_tag_key)
    assert rule.name == "fiction-fantasy"
    assert rule.add_tags == ["/tags/OL183T", "/tags/OL169T"]
    assert rule.selector_strings == ["Fiction - Fantasy", "Fantasy fiction"]
    assert rule.subjects_to_remove() == {"Fiction - Fantasy"}  # only the 0-flagged one


# --- tag -> field routing ---------------------------------------------------


def test_resolve_tags_routes_by_tag_type():
    ol = FakeOL(tags={"OL183T": FICTION, "OL169T": FANTASY})
    field, ttype, name = resolve_tags(ol, ["/tags/OL183T", "/tags/OL169T"])
    assert field["/tags/OL183T"] == "literary_forms"
    assert field["/tags/OL169T"] == "genres"


def test_resolve_tags_unknown_type_raises():
    ol = FakeOL(tags={"OL9T": tag("not_a_type", "X")})
    with pytest.raises(ValueError, match="maps to no work field"):
        resolve_tags(ol, ["/tags/OL9T"])


# --- planning ---------------------------------------------------------------


def test_multiple_subjects_union_and_dedup():
    ol = FakeOL(
        tags={"OL184T": NONFIC},
        subjects=HITS,
        subject_works={
            "Nonfiction": ["/works/OL1W", "/works/OL2W"],
            "Non-fiction": ["/works/OL2W", "/works/OL3W"],
        },
        work_docs={"OL1W": {"revision": 1}, "OL2W": {"revision": 1}, "OL3W": {"revision": 1}},
    )
    rule = Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction", "Non-fiction"])
    plan = plan_rule(ol, rule, limit=50)
    assert [c.work_key for c in plan.changes] == ["/works/OL1W", "/works/OL2W", "/works/OL3W"]
    assert plan.subject_counts == {"Nonfiction": 38920, "Non-fiction": 1200}


def test_plan_rule_batches_reads_with_get_many():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W", "/works/OL2W", "/works/OL3W"]},
        work_docs={"OL1W": {"revision": 1}, "OL2W": {"revision": 1}, "OL3W": {"revision": 1}},
    )
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    # one batched fetch of all three keys — not a GET per work
    assert ol.get_many_calls == [["/works/OL1W", "/works/OL2W", "/works/OL3W"]]
    # the fetched doc is carried on each WorkChange for reuse
    assert all(c.doc is not None for c in plan.changes)


def test_build_save_docs_reuses_plan_doc_without_refetch():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 1}},
    )
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    n_before = len(ol.get_many_calls)
    build_save_docs(ol, plan, comment="c")
    assert len(ol.get_many_calls) == n_before  # reused c.doc, issued no new fetch


def test_apply_rule_skips_work_edited_since_planning():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W", "/works/OL2W"]},
        work_docs={"OL1W": {"revision": 1}, "OL2W": {"revision": 1}},
        user="/people/openlibrarytagsbot",
    )
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    # OL2W is edited by someone else between plan and save (revision moves on)
    ol._work_docs["OL2W"] = {"revision": 9}
    stats = apply_rule(ol, plan, comment="c", dry_run=False,
                       expected_account="openlibrarytagsbot")
    written_keys = [d["key"] for batch in ol.saved for d in batch]
    assert written_keys == ["/works/OL1W"]  # stale OL2W skipped by the lost-update guard
    assert stats["written"] == 1


def test_multiple_tags_hit_their_own_fields():
    ol = FakeOL(
        tags={"OL183T": FICTION, "OL169T": FANTASY},
        subjects=HITS,
        subject_works={"Fiction - Fantasy": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 5}},
    )
    rule = Rule(add_tags=["/tags/OL183T", "/tags/OL169T"], subjects=[("Fiction - Fantasy", 0)])
    plan = plan_rule(ol, rule, limit=50)
    tc = plan.changes[0].tag_changes
    assert tc["literary_forms"][1] == ["/tags/OL183T"]
    assert tc["genres"][1] == ["/tags/OL169T"]


def test_add_is_idempotent_noop():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 2, "literary_forms": [{"key": "/tags/OL184T"}]}},
    )
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    assert plan.to_write == []
    assert plan.noop_count == 1


def test_keep_flag_1_removes_nothing():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 1, "subjects": ["Nonfiction", "Essays"]}},
    )
    rule = Rule(add_tags=["/tags/OL184T"], subjects=[("Nonfiction", 1)])  # keep
    plan = plan_rule(ol, rule, limit=50)
    assert plan.changes[0].subject_changes == {}
    assert build_save_docs(ol, plan, "c")[0]["subjects"] == ["Nonfiction", "Essays"]


def test_flag_0_removes_only_that_subject():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Non-fiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 1, "subjects": ["Nonfiction", "Non-fiction", "Essays"]}},
    )
    rule = Rule(add_tags=["/tags/OL184T"], subjects=[("Non-fiction", 0), ("Nonfiction", 1)])
    plan = plan_rule(ol, rule, limit=50)
    _before, after = plan.changes[0].subject_changes["subjects"]
    assert after == ["Nonfiction", "Essays"]  # only "Non-fiction" removed


# --- save docs + writing ----------------------------------------------------


def test_build_save_docs_is_raw_and_lossless():
    ol = FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W"]},
        work_docs={"OL1W": {
            "revision": 1, "title": "Keep me", "subjects": ["Nonfiction"],
            "description": {"type": "/type/text", "value": "x"},
        }},
    )
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    doc = build_save_docs(ol, plan, comment="migrate")[0]
    assert doc["title"] == "Keep me"
    assert doc["description"] == {"type": "/type/text", "value": "x"}
    assert doc["literary_forms"] == [{"key": "/tags/OL184T"}]
    assert doc["key"] == "/works/OL1W"
    # The comment rides the 42-comment header, not a per-doc property
    # (/api/save_many rejects _comment as bad_data).
    assert "_comment" not in doc


def _one_work_ol(user=None):
    return FakeOL(
        tags={"OL184T": NONFIC}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 1, "subjects": ["Nonfiction"]}},
        user=user,
    )


def test_dry_run_writes_nothing():
    ol = _one_work_ol()
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    summary = apply_rule(ol, plan, comment="c", dry_run=True)
    assert summary == {"dry_run": True, "would_write": 1, "batches": 1}
    assert ol.saved == []


def test_write_skips_lost_update():
    ol = _one_work_ol("/people/openlibrarytagsbot,2026,h")
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    ol._work_docs["OL1W"]["revision"] = 2
    summary = apply_rule(ol, plan, comment="c", dry_run=False, expected_account="openlibrarytagsbot")
    assert summary["written"] == 0


def test_logged_in_user_parses_session_cookie():
    ol = _one_work_ol("/people/openlibrarytagsbot,2026-01-01,hash")
    assert logged_in_user(ol) == "/people/openlibrarytagsbot"


@pytest.mark.parametrize("cookie,expected", [
    ("/people/mek,2026-01-01,hash", "/people/mek"),      # normal
    ("%2Fpeople%2Fmek,ts,h", "/people/mek"),             # url-encoded
    ('"/people/mek,ts,h"', "/people/mek"),               # quoted
    (None, None),                                          # not logged in
    ("", None),                                            # empty
    ("garbage-no-people", None),                           # unparseable
])
def test_logged_in_user_edge_cases(cookie, expected):
    assert logged_in_user(_one_work_ol(cookie)) == expected


def test_write_refuses_wrong_identity():
    ol = _one_work_ol("/people/someone_else,2026,hash")
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    with pytest.raises(SystemExit, match="identity check FAILED"):
        apply_rule(ol, plan, comment="c", dry_run=False, expected_account="openlibrarytagsbot")
    assert ol.saved == []


def test_write_proceeds_for_correct_identity_and_posts_save_many():
    ol = _one_work_ol("/people/openlibrarytagsbot,2026,hash")
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    summary = apply_rule(ol, plan, comment="c", dry_run=False, expected_account="openlibrarytagsbot")
    assert summary["written"] == 1
    assert ol.saved[0][0]["literary_forms"] == [{"key": "/tags/OL184T"}]


def test_failed_post_writes_no_audit_row(tmp_path):
    ol = _one_work_ol("/people/openlibrarytagsbot,2026,hash")

    def boom(url, data=None, headers=None):
        def raise_for_status():
            raise RuntimeError("400 bad_data")
        return types.SimpleNamespace(status_code=400, raise_for_status=raise_for_status)

    ol.session = types.SimpleNamespace(post=boom, cookies=ol.session.cookies)
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    audit = tmp_path / "audit.jsonl"
    with pytest.raises(RuntimeError, match="400"):
        apply_rule(ol, plan, comment="c", dry_run=False,
                   expected_account="openlibrarytagsbot", audit=str(audit))
    # No phantom "we changed this" row: the file was never written to.
    assert not audit.exists() or audit.read_text() == ""


def test_add_subjects_removes_loser_and_appends_winner():
    # the string->string merge: remove "Non-fiction", add "Nonfiction"
    ol = FakeOL(
        tags={}, subjects=HITS,
        subject_works={"Non-fiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 1, "subjects": ["Non-fiction", "Essays"]}},
    )
    rule = Rule(add_tags=[], subjects=[("Non-fiction", 0)], add_subjects=["Nonfiction"])
    plan = plan_rule(ol, rule, limit=50)
    _before, after = plan.changes[0].subject_changes["subjects"]
    assert after == ["Essays", "Nonfiction"]
    assert build_save_docs(ol, plan, "c")[0]["subjects"] == ["Essays", "Nonfiction"]


def test_add_subjects_is_idempotent_noop():
    ol = FakeOL(
        tags={}, subjects=HITS,
        subject_works={"Nonfiction": ["/works/OL1W"]},
        work_docs={"OL1W": {"revision": 1, "subjects": ["Nonfiction", "Essays"]}},
    )
    rule = Rule(add_tags=[], subjects=[("Nonfiction", 1)], add_subjects=["Nonfiction"])
    plan = plan_rule(ol, rule, limit=50)
    assert plan.to_write == [] and plan.noop_count == 1


def test_save_many_request_shape():
    ol = _one_work_ol()
    plan = plan_rule(ol, Rule(add_tags=["/tags/OL184T"], subjects=["Nonfiction"]), limit=50)
    docs = build_save_docs(ol, plan, comment="migrate")
    req = save_many_request(ol, docs, comment="migrate")
    assert req["url"].endswith("/api/save_many")
    assert req["headers"]["42-comment"] == "migrate"
    assert req["body"][0]["key"] == "/works/OL1W"
