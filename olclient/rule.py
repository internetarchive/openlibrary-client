"""
rule.py

A **rule** pairs a *selector* (which works) with a *change* (what to do to them).
It is declarative and re-runnable: applying it twice converges to the same state,
because adds are a de-duplicated merge and removes are a set difference.

A rule is a small YAML document -- saveable, reviewable, checked in, and (later)
run by the import pipeline to remediate records as they arrive:

    rule: fiction-fantasy
    subject_type: subject            # optional, default "subject"
    subjects:
      - ["Fiction - Fantasy", 0]     # 1 = keep the subject, 0 = remove it
      - ["Fantasy fiction", 1]       # selects on it, leaves it in place
    tags:
      - literary_form:fiction        # <tag_type>:<slug>, or a /tags/OL..T key
      - genre:fantasy

Semantics:
  * **select** the works carrying ANY of the listed subjects (the union),
  * **add** every listed Tag -- each routed to the right work field by its tag_type
    (``genre`` -> ``genres``, ``literary_form`` -> ``literary_forms`` ...), and
  * **remove** the subjects flagged 0; leave the subjects flagged 1.

Everything is driven through an injected ``ol`` (an olclient ``OpenLibrary``), so
the engine unit-tests against a fake client with no network. The read/preview path
hits only public endpoints; writing (:func:`apply_rule`) requires auth, asserts the
bot identity, and is dry-run-able.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from urllib.parse import unquote

SAVE_MANY_PATH = "/api/save_many"

# Open Library's ModSecurity WAF denies a POST (HTTP 460, rule 200007) when the
# parsed request body exceeds SecArgumentsLimit (6000 args). ModSec counts one
# arg per JSON leaf, so a save_many batch's arg total is the sum of its docs'
# leaves. We pack batches to stay under this budget (with margin).
SAVE_MANY_ARG_BUDGET = 5000


def _leaf_count(obj) -> int:
    """Number of scalar leaves in a JSON-ish object (== ModSec's arg count)."""
    if isinstance(obj, dict):
        return sum(_leaf_count(v) for v in obj.values()) or 1
    if isinstance(obj, list):
        return sum(_leaf_count(v) for v in obj) or 1
    return 1


def pack_batches(docs, max_count, arg_budget=SAVE_MANY_ARG_BUDGET):
    """Group docs into save_many batches bounded by BOTH a doc count and the
    WAF arg budget, so a cluster of heavy works can't push a POST over the
    SecArgumentsLimit. A lone doc larger than the budget is still yielded
    alone (a single doc can't be split)."""
    batch, args = [], 0
    for doc in docs:
        n = _leaf_count(doc)
        if batch and (len(batch) >= max_count or args + n > arg_budget):
            yield batch
            batch, args = [], 0
        batch.append(doc)
        args += n
    if batch:
        yield batch

# A Tag's singular ``tag_type`` -> the plural work field it belongs in. An unmapped
# tag_type is an error (never a guessed field).
TAG_TYPE_TO_FIELD = {
    "genre": "genres",
    "subgenre": "subgenres",
    "audience": "audiences",
    "content_warning": "content_warnings",
    "content_format": "content_formats",
    "literary_form": "literary_forms",
    "award": "awards",
}

# Which work field holds each subject_type's free-text strings.
SUBJECT_TYPE_FIELD = {
    "subject": "subjects",
    "person": "subject_people",
    "place": "subject_places",
    "time": "subject_times",
}


@dataclass
class SubjectSel:
    """One selector subject plus whether it survives: keep (True) or remove (False)."""

    name: str
    keep: bool = True


def subject_slug(name: str) -> str:
    """Open Library's ``/subjects/<slug>`` key for a subject string.

    Lowercases, turns every run of non-alphanumeric characters into a single
    underscore, and trims leading/trailing underscores -- so ``'Art, German'``
    -> ``'art_german'`` and ``'Graphic design'`` -> ``'graphic_design'``. Used
    to match subjects for removal by slug (as ``--rm-subjects`` gives them).
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


@dataclass
class Rule:
    add_tags: list[str]  # resolved Tag keys, e.g. ['/tags/OL183T']
    subjects: list  # SubjectSel | str | (str, 0|1); normalised in __post_init__
    add_subjects: list[str] = dc_field(default_factory=list)  # plain subject strings to add
    remove_subject_slugs: list[str] = dc_field(default_factory=list)  # drop subjects by slug
    name: str | None = None
    subject_type: str = "subject"

    def __post_init__(self):
        norm = []
        for item in self.subjects:
            if isinstance(item, SubjectSel):
                norm.append(item)
            elif isinstance(item, (list, tuple)):
                norm.append(SubjectSel(str(item[0]), keep=bool(int(item[1]))))
            else:
                norm.append(SubjectSel(str(item), keep=True))
        self.subjects = norm

    @property
    def selector_strings(self) -> list[str]:
        return [s.name for s in self.subjects]

    def subjects_to_remove(self) -> set[str]:
        return {s.name for s in self.subjects if not s.keep}


def resolve_tag_ref(ref: str, slug_to_tag_key) -> str:
    """Resolve a ``<tag_type>:<slug>`` ref (or a ``/tags/OL..T`` key) to a Tag key.

    ``slug_to_tag_key(vocab_dir, slug)`` looks a slug up in a vocabulary. The vocab
    directory name is tried as the tag_type and as its plural, so both the singular
    ``literary_form`` and the plural ``genres`` vocab dirs resolve.
    """
    ref = ref.strip()
    if ref.startswith("/tags/"):
        return ref
    if ":" in ref:
        tag_type, slug = ref.split(":", 1)
    elif "/" in ref:  # tolerate the older type/slug form
        tag_type, slug = ref.split("/", 1)
    else:
        raise ValueError(f"tag ref {ref!r} must be <tag_type>:<slug> or /tags/OL..T")
    for vocab_dir in (tag_type, tag_type + "s"):
        key = slug_to_tag_key(vocab_dir, slug)
        if key:
            return key
    raise ValueError(f"no Tag found for {ref!r}")


def load_rule(path: str, slug_to_tag_key) -> Rule:
    """Load a rule from a YAML file, resolving its tag refs to Tag keys."""
    import yaml

    data = yaml.safe_load(Path(path).read_text()) or {}
    tags = [resolve_tag_ref(str(t), slug_to_tag_key) for t in data.get("tags", [])]
    return Rule(
        add_tags=tags,
        subjects=data.get("subjects", []),
        add_subjects=[str(s) for s in data.get("add_subjects", [])],
        name=data.get("rule") or data.get("name"),
        subject_type=data.get("subject_type", "subject"),
    )


@dataclass
class WorkChange:
    work_key: str
    revision: int | None
    tag_changes: dict[str, tuple[list[str], list[str]]] = dc_field(default_factory=dict)
    subject_changes: dict[str, tuple[list[str], list[str]]] = dc_field(default_factory=dict)

    @property
    def is_noop(self) -> bool:
        both = list(self.tag_changes.values()) + list(self.subject_changes.values())
        return all(before == after for before, after in both)


@dataclass
class RulePlan:
    rule: Rule
    tag_field: dict[str, str]
    tag_type: dict[str, str]
    tag_name: dict[str, str]
    subject_counts: dict[str, int | None]
    changes: list[WorkChange] = dc_field(default_factory=list)

    @property
    def to_write(self) -> list[WorkChange]:
        return [c for c in self.changes if not c.is_noop]

    @property
    def noop_count(self) -> int:
        return sum(1 for c in self.changes if c.is_noop)


def _olid(work_key: str) -> str:
    return work_key.rstrip("/").split("/")[-1]


def logged_in_user(ol) -> str | None:
    """The /people/<name> the session is authenticated as, or None."""
    try:
        raw = ol.session.cookies.get("session")
    except Exception:
        raw = None
    if raw:
        m = re.match(r"(/people/[A-Za-z0-9_.\-]+)", unquote(raw).strip().strip('"'))
        if m:
            return m.group(1)
    return None


def assert_identity(ol, expected_account: str) -> str:
    """Abort before any write unless the session really is ``expected_account``."""
    expected = expected_account if expected_account.startswith("/people/") else f"/people/{expected_account}"
    who = logged_in_user(ol)
    if who is None or who.lower() != expected.lower():
        raise SystemExit(
            f"identity check FAILED: session is {who!r}, expected {expected!r} — refusing to write"
        )
    return who


def resolve_tags(ol, tag_keys):
    """Resolve each Tag key to its (field, tag_type, name) by reading the Tag."""
    tag_field, tag_type, tag_name = {}, {}, {}
    for key in tag_keys:
        tag = ol.Tag.get(_olid(key))
        if tag is None:
            raise ValueError(f"Tag {key} does not exist")
        ttype = getattr(tag, "tag_type", None)
        try:
            field = TAG_TYPE_TO_FIELD[ttype]
        except KeyError:
            raise ValueError(
                f"Tag {key} has tag_type {ttype!r}, which maps to no work field; "
                f"known: {sorted(TAG_TYPE_TO_FIELD)}"
            )
        tag_field[key] = field
        tag_type[key] = ttype
        tag_name[key] = getattr(tag, "name", None) or key
    return tag_field, tag_type, tag_name


def _merge_keys(existing, add_keys):
    current = [e["key"] if isinstance(e, dict) else e for e in (existing or [])]
    return list(dict.fromkeys(current + list(add_keys)))


def _select_work_keys(ol, rule: Rule, limit):
    """Union of works carrying ANY selector subject, de-duped, capped at limit."""
    seen = {}
    for subject in rule.selector_strings:
        for key in ol.works_by_subject(subject, subject_type=rule.subject_type, limit=limit):
            if key not in seen:
                seen[key] = True
                if limit is not None and len(seen) >= limit:
                    return list(seen)
    return list(seen)


def plan_rule(ol, rule: Rule, limit=50, work_keys=None):
    """Compute (read-only) what ``rule`` would change, over up to ``limit`` works.

    ``work_keys`` lets a caller inject an already-selected set of works (e.g.
    ``ol tag add``, which selects via ``/search.json``) instead of the default
    subject-union selection. When given, it is used verbatim, capped at ``limit``.
    """
    tag_field, tag_type, tag_name = resolve_tags(ol, rule.add_tags)

    subject_counts: dict[str, int | None] = {}
    for subject in rule.selector_strings:
        hits = list(ol.search_subjects(subject, limit=25, subject_type=rule.subject_type))
        count = None
        for hit in hits:  # exact case first (case-only variants are distinct subjects)
            if hit.get("name") == subject:
                count = hit.get("work_count")
                break
        if count is None:
            for hit in hits:
                if hit.get("name", "").lower() == subject.lower():
                    count = hit.get("work_count")
                    break
        subject_counts[subject] = count

    drop = rule.subjects_to_remove()
    drop_slugs = {subject_slug(s) for s in rule.remove_subject_slugs}
    adds = list(rule.add_subjects)
    subj_field = SUBJECT_TYPE_FIELD.get(rule.subject_type, "subjects")

    if work_keys is None:
        selected = _select_work_keys(ol, rule, limit)
    else:
        selected = list(dict.fromkeys(work_keys))[:limit] if limit is not None else list(dict.fromkeys(work_keys))

    changes = []
    for work_key in selected:
        data = ol.get_ol_response(f"/works/{_olid(work_key)}.json").json()

        tag_changes = {}
        for key in rule.add_tags:
            field = tag_field[key]
            before = [e["key"] if isinstance(e, dict) else e for e in data.get(field, [])]
            after = _merge_keys(data.get(field, []), [key])
            tag_changes[field] = (before, after)

        subject_changes = {}
        if drop or drop_slugs or adds:
            before = list(data.get(subj_field, []))
            after = [s for s in before if s not in drop and subject_slug(s) not in drop_slugs]
            for a in adds:
                if a not in after:
                    after.append(a)
            if before != after:
                subject_changes[subj_field] = (before, after)

        changes.append(
            WorkChange(
                work_key=work_key,
                revision=data.get("revision"),
                tag_changes=tag_changes,
                subject_changes=subject_changes,
            )
        )
    return RulePlan(
        rule=rule,
        tag_field=tag_field,
        tag_type=tag_type,
        tag_name=tag_name,
        subject_counts=subject_counts,
        changes=changes,
    )


def format_plan(plan: RulePlan, limit: int) -> str:
    r = plan.rule
    lines = [f"RULE{(' ' + r.name) if r.name else ''}", "  select works with any of these subjects:"]
    for s in r.subjects:
        count = plan.subject_counts.get(s.name)
        shown = f"{count:,}" if isinstance(count, int) else "?"
        flag = "keep" if s.keep else "REMOVE"
        lines.append(f"    - {s.name!r}  [{flag}]  ({shown} works)")
    lines.append(f"    (subject_type: {r.subject_type})")
    if r.add_tags:
        lines.append("  add tags:")
        for key in r.add_tags:
            lines.append(
                f"    {plan.tag_name[key]} ({plan.tag_type[key]})  {key}  -> field '{plan.tag_field[key]}'"
            )
    if r.add_subjects:
        lines.append("  add subjects:")
        for s in r.add_subjects:
            lines.append(f"    {s!r}  -> field '{SUBJECT_TYPE_FIELD.get(r.subject_type, 'subjects')}'")
    lines.append("")
    enumerated = len(plan.changes)
    capped = "  (capped by --limit)" if enumerated >= limit else ""
    lines.append(f"Unique works examined this run: {enumerated:,}{capped}")
    lines.append(f"  would change: {len(plan.to_write):,}   already satisfied (no-op): {plan.noop_count:,}")
    lines.append("")
    lines.append("SAMPLE CHANGES:")
    for c in plan.to_write[:10]:
        parts = []
        for field, (before, after) in c.tag_changes.items():
            added = [k for k in after if k not in before]
            if added:
                parts.append(f"{field} +{', '.join(added)}")
        for field, (before, after) in c.subject_changes.items():
            removed = [s for s in before if s not in after]
            added = [s for s in after if s not in before]
            if removed:
                parts.append(f"{field} -{', '.join(removed)}")
            if added:
                parts.append(f"{field} +{', '.join(added)}")
        lines.append(f"  {c.work_key} @rev{c.revision}  {'; '.join(parts)}")
    if not plan.to_write:
        lines.append("  (none — every examined work already satisfies the rule)")
    return "\n".join(lines)


def build_save_docs(ol, plan: RulePlan, comment: str):
    """Build the raw work dicts a write would POST to /api/save_many (lossless)."""
    docs = []
    for c in plan.to_write:
        data = ol.get_ol_response(f"/works/{_olid(c.work_key)}.json").json()
        data["key"] = c.work_key
        for field, (_before, after) in c.tag_changes.items():
            data[field] = [{"key": k} for k in after]
        for field, (_before, after) in c.subject_changes.items():
            data[field] = list(after)
        # NB: the edit comment travels in the "42-comment" header, NOT as a
        # per-doc "_comment" property — /api/save_many rejects that as bad_data.
        docs.append(data)
    return docs


def save_many_request(ol, docs, comment):
    """The exact /api/save_many request a write would send (inspectable; sends nothing)."""
    return {
        "method": "POST",
        "url": ol.base_url + SAVE_MANY_PATH,
        "headers": {
            "Opt": '"http://openlibrary.org/dev/docs/api"; ns=42',
            "42-comment": comment,
        },
        "body": docs,
    }


def _audit_rows(plan: RulePlan, comment: str):
    rows = {}
    for c in plan.to_write:
        changes = {}
        for field, (before, after) in {**c.tag_changes, **c.subject_changes}.items():
            if before != after:
                changes[field] = {"before": before, "after": after}
        rows[c.work_key] = {
            "work": c.work_key, "base_revision": c.revision,
            "comment": comment, "changes": changes,
        }
    return rows


def apply_rule(ol, plan: RulePlan, comment: str, batch_size=250, dry_run=True,
               audit=None, expected_account=None):
    """Apply a plan. DRY RUN unless ``dry_run=False``. Returns a summary dict.

    Safety: refuses to write unless the session is ``expected_account`` (when given);
    re-fetches and compares each work's revision immediately before saving (lost-update
    guard); writes in batches of ``batch_size`` via /api/save_many; writes a reversible
    audit record (base revision + per-field before/after) after each accepted batch
    when ``audit`` (a file path) is given.
    """
    docs = build_save_docs(ol, plan, comment)
    if dry_run:
        return {
            "dry_run": True,
            "would_write": len(docs),
            "batches": sum(1 for _ in pack_batches(docs, batch_size)),
        }

    if expected_account:
        assert_identity(ol, expected_account)

    audit_rows = _audit_rows(plan, comment)
    written = 0
    for batch in pack_batches(docs, batch_size):
        safe = []
        for doc in batch:
            key = doc["key"]
            live = ol.get_ol_response(f"{key}.json").json()
            planned = next((c for c in plan.to_write if c.work_key == key), None)
            if planned is not None and live.get("revision") != planned.revision:
                continue
            safe.append(doc)
        req = save_many_request(ol, safe, comment)
        resp = ol.session.post(req["url"], json.dumps(safe), headers=req["headers"])
        resp.raise_for_status()
        # Audit only AFTER the batch is accepted, so a rejected/failed POST
        # never leaves a phantom "we changed this" row.
        if audit:
            with open(audit, "a", encoding="utf-8") as fh:
                for doc in safe:
                    fh.write(json.dumps(audit_rows[doc["key"]]) + "\n")
        written += len(safe)
    return {"dry_run": False, "written": written, "planned": len(docs)}
