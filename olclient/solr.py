"""Shared access to Open Library's Solr core (read-only).

`ol search` is the Solr-backed verb. It talks to the core at $OL_SOLR_BASE_URL
(e.g. http://solr:8983/solr/openlibrary); the public openlibrary.org proxy does
not expose /solr, so these run where the core is reachable. The datastore
(infogami /query.json, Tag.find, full records) is a separate concern — see the
INFOGAMI_TYPES note in ol.search.
"""

import json
import os
import urllib.request


def solr_base(explicit=None):
    base = explicit or os.environ.get("OL_SOLR_BASE_URL")
    if not base:
        raise SystemExit(
            "no Solr base URL: set OL_SOLR_BASE_URL "
            "(e.g. http://solr:8983/solr/openlibrary) or pass --solr"
        )
    return base.rstrip("/")


def http_get_json(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (internal Solr)
        return json.loads(resp.read())
