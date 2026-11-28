"""`ol search <type>` — the Solr-backed search verb.

The Solr core only indexes three doc types — ``work``, ``author``, ``subject``
— so those are the entity types search owns:

  * works / authors  -> ordinary doc search (q, filtered by type, return docs)
  * subjects         -> a facet over ``subject_facet`` (every subject string +
                        its work_count), with ``--query`` (substring) and
                        ``--max-works`` (count ceiling)

``editions`` and ``tags`` are NOT in the search index — editions live *inside*
work docs, tags are ``/type/tag`` datastore objects. They belong to infogami
(``/query.json`` / ``Tag.find``), so ``ol search`` refuses them explicitly
rather than pretending. That refusal is the search-vs-infogami boundary.
"""

import json
import urllib.parse

SUBJECT_FACET = "subject_facet"
WORK_DOMAIN = "type:work"  # count works, so a subject bucket's count == work_count

# Entity types Solr owns, with the type filter and the fields worth showing.
DOC_TYPES = {
    "works": {"fq": "type:work", "fields": ["key", "title", "author_name"]},
    "authors": {"fq": "type:author", "fields": ["key", "name"]},
}

# Entity types that are NOT in the search index — infogami/datastore territory.
INFOGAMI_TYPES = {
    "editions": "editions aren't top-level search docs (they live inside work "
                "docs); query infogami /query.json instead",
    "tags": "tags are /type/tag datastore objects (not in Solr); use infogami "
            "Tag.find / /query.json instead",
}

ENTITY_CHOICES = ["subjects", "works", "editions", "authors", "tags"]


# --- doc search (works, authors) --------------------------------------------

def search_docs(get, base, entity, query=None, limit=None):
    spec = DOC_TYPES[entity]
    params = {
        "q": query or "*:*",
        "fq": spec["fq"],
        "fl": ",".join(spec["fields"]),
        "rows": limit if limit is not None else 20,
        "wt": "json",
    }
    data = get(f"{base}/select?{urllib.parse.urlencode(params)}")
    return data.get("response", {}).get("docs", [])


# --- subject facet search ---------------------------------------------------

def _json_facet_url(base, sort, limit, offset):
    jf = {"s": {"type": "terms", "field": SUBJECT_FACET, "sort": sort,
                "mincount": 1, "limit": limit, "offset": offset}}
    qs = urllib.parse.urlencode({
        "q": WORK_DOMAIN, "rows": 0, "wt": "json", "json.facet": json.dumps(jf),
    })
    return f"{base}/select?{qs}"


def _contains_facet_url(base, query, limit):
    qs = urllib.parse.urlencode({
        "q": WORK_DOMAIN, "rows": 0, "wt": "json", "facet": "true",
        "facet.field": SUBJECT_FACET, "facet.contains": query,
        "facet.contains.ignoreCase": "true", "facet.limit": limit,
        "facet.mincount": 1, "facet.sort": "count",
    })
    return f"{base}/select?{qs}"


def iter_subjects(get, base, max_works=None, sort="count asc", page=1000):
    """Yield ``(name, work_count)`` for regular subjects, in ``sort`` order.

    With ascending sort and a ``max_works`` ceiling, stop as soon as a bucket's
    count exceeds it — so listing the rare tail pulls only the rare buckets.
    """
    ascending = sort.strip().endswith("asc")
    offset = 0
    while True:
        data = get(_json_facet_url(base, sort, page, offset))
        buckets = data.get("facets", {}).get("s", {}).get("buckets", [])
        if not buckets:
            return
        for b in buckets:
            count = b["count"]
            if max_works is not None and count > max_works:
                if ascending:
                    return
                continue
            yield b["val"], count
        offset += len(buckets)


def search_subjects(get, base, query=None, max_works=None, limit=None, page=1000):
    """Regular subjects as ``(name, work_count)``, rarest first.

    With ``query`` (substring, case-insensitive) the matching set is small, so
    we pull it in one faceted request and filter locally. Without a query we
    page the whole field count-ascending with an early stop on ``max_works``.
    """
    if query:
        data = get(_contains_facet_url(base, query, -1))
        flat = data.get("facet_counts", {}).get("facet_fields", {}).get(SUBJECT_FACET, [])
        pairs = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
        pairs = [(n, c) for n, c in pairs if max_works is None or c <= max_works]
        pairs.sort(key=lambda nc: nc[1])  # rarest first
        return pairs[:limit] if limit is not None else pairs

    out = []
    for name, count in iter_subjects(get, base, max_works=max_works, sort="count asc", page=page):
        out.append((name, count))
        if limit is not None and len(out) >= limit:
            break
    return out
