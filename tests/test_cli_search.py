"""Tests for `ol search` (ol/search.py), driven through a fake Solr getter.

No network. Covers the subject facet (count-asc paging early-stop, --query
substring via facet.contains, --max-works, --limit), generic doc search for
works/authors, and the search-vs-infogami boundary (editions/tags refused).
"""

import json
import urllib.parse

import pytest

from olclient.cli import build_parser, cmd_search
from olclient.search import (
    INFOGAMI_TYPES,
    search_docs,
    search_subjects,
)


# subject vocabulary: (name, work_count), used by the fake Solr.
VOCAB = [
    ("Appel public a l'epargne", 1),
    ("Comic fantasy", 3),
    ("High fantasy", 7),
    ("Epic Fantasy", 10),
    ("Fantasy", 13566),
    ("Fiction, fantasy, general", 55470),
    ("Cooking", 2),
]


def fake_solr(vocab=VOCAB, docs=None):
    def get(url):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        # JSON Facet path (no query): count-asc/desc paging
        if "json.facet" in qs:
            jf = json.loads(qs["json.facet"][0])["s"]
            sort, limit, offset = jf["sort"], jf["limit"], jf["offset"]
            rows = sorted(vocab, key=lambda x: x[1], reverse=sort.endswith("desc"))
            page = rows[offset:offset + limit]
            return {"facets": {"s": {"buckets": [{"val": n, "count": c} for n, c in page]}}}
        # classic facet.contains path (--query on subjects)
        if qs.get("facet", [None])[0] == "true":
            sub = qs["facet.contains"][0].lower()
            flat = []
            for n, c in sorted(vocab, key=lambda x: -x[1]):
                if sub in n.lower():
                    flat += [n, c]
            return {"facet_counts": {"facet_fields": {"subject_facet": flat}}}
        # doc search path
        return {"response": {"docs": docs or []}}

    return get


# --- subjects: no-query enumeration ----------------------------------------

def test_subjects_max_works_rarest_first_early_stop():
    rows = search_subjects(fake_solr(), "http://s", max_works=10)
    assert [c for _, c in rows] == [1, 2, 3, 7, 10]  # excludes 13566/55470


def test_subjects_limit_caps():
    rows = search_subjects(fake_solr(), "http://s", max_works=10, limit=2)
    assert len(rows) == 2 and rows[0][1] == 1


# --- subjects: --query (substring via facet.contains) ----------------------

def test_subjects_query_substring_and_maxworks():
    rows = search_subjects(fake_solr(), "http://s", query="fantasy", max_works=10)
    names = [n for n, _ in rows]
    assert "Cooking" not in names            # filtered by substring
    assert "Fantasy" not in names            # 13566 > max_works
    assert set(names) == {"Comic fantasy", "High fantasy", "Epic Fantasy"}
    assert [c for _, c in rows] == [3, 7, 10]  # rarest first


def test_subjects_query_without_maxworks_returns_all_matches():
    rows = search_subjects(fake_solr(), "http://s", query="fantasy")
    assert len(rows) == 5  # all 5 fantasy-containing subjects


# --- works / authors doc search --------------------------------------------

def test_search_docs_works():
    docs = [{"key": "/works/OL1W", "title": "Dune", "author_name": ["Frank Herbert"]}]
    rows = search_docs(fake_solr(docs=docs), "http://s", "works", query="dune", limit=5)
    assert rows[0]["key"] == "/works/OL1W"


# --- search vs infogami boundary -------------------------------------------

@pytest.mark.parametrize("entity", ["editions", "tags"])
def test_infogami_types_are_refused(entity, capsys):
    args = build_parser().parse_args(["search", entity])
    with pytest.raises(SystemExit) as e:
        cmd_search(args)
    assert entity in str(e.value) and "infogami" in str(e.value)
    assert entity in INFOGAMI_TYPES


def test_search_subjects_requires_a_bound():
    import types
    import pytest
    from olclient.cli import cmd_search
    args = types.SimpleNamespace(type="subjects", query=None, max_works=None,
                                 limit=None, solr="http://s", json=False)
    with pytest.raises(SystemExit, match="unbounded"):
        cmd_search(args)
