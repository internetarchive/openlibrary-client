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
    plan_rule,
    resolve_tag_ref,
    resolve_tags,
    save_many_request,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeTagAPI:
    def __init__(self, tags):
        self._tags = tags

    def get(self, olid):
        return self._tags.get(olid)


class FakeOL:
    def __init__(self, tags=None, subjects=None, subject_works=None, work_docs=None, user=None):
        self.Tag = FakeTagAPI(tags or {})
        self._subjects = subjects or []
        self._subject_works = subject_works or {}
        self._work_docs = work_docs or {}
        self.base_url = "https://openlibrary.org"
        self.saved = []
        cookies = types.SimpleNamespace(get=lambda name: user)
        self.session = types.SimpleNamespace(post=self._post, cookies=cookies)

    def search_subjects(self, q, limit=10, subject_type=None):
        return [h for h in self._subjects if h["name"].lower() == q.lower()]

    def works_by_subject(self, subject, subject_type="subject", limit=None):
        keys = self._subject_works.get(subject, [])
        yield from (keys if limit is None else keys[:limit])

    def get_ol_response(self, path):
        olid = path.rstrip("/").split("/")[-1].removesuffix(".json")
        return FakeResponse(self._work_docs[olid])

    def _post(self, url, data=None, headers=None):
        self.saved.append(json.loads(data))
        return types.SimpleNamespace(status_code=200, raise_for_status=lambda: None)


def tag(tag_type, name):
    return types.SimpleNamespace(tag_type=tag_type, name=name)


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


def test_resolve_tag_ref_colon_form_singular_and_plural_dirs():
    # literary_form resolves from the singular dir; genre from the plural dir.
    assert resolve_tag_ref("literary_form:fiction", fake_slug_to_tag_key) == "/tags/OL183T"
    assert resolve_tag_ref("genre:fantasy", fake_slug_to_tag_key) == "/tags/OL169T"


def test_resolve_tag_ref_passes_through_key():
    assert resolve_tag_ref("/tags/OL184T", fake_slug_to_tag_key) == "/tags/OL184T"


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
