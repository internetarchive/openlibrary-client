"""
imports.py
~~~~~~~~~~

Base classes for Open Library bulk import adapters.

Architecture mirrors pyopds2 / pyopds2_openlibrary:

  DataProvider        — abstract traversal layer (JSONL, OPDS, paginated API, …)
  DataProviderRecord  — abstract per-record layer; maps source schema → OLImportRecord
  OLImportRecord      — Pydantic model mirroring openlibrary/schemata/import.schema.json
  JSONLProvider       — mixin: streams a local path or remote URL line-by-line

Concrete source adapters live in openlibrary-bots/sources/<slug>/ and import from
this module.

Usage::

    from olclient.imports import JSONLProvider, DataProviderRecord, OLImportRecord, OLAuthor

    class MyRecord(DataProviderRecord):
        title: str
        ...
        def to_ol_import(self) -> OLImportRecord | None:
            ...

    class MyProvider(JSONLProvider):
        SOURCE_SLUG = "mysource"
        TITLE = "My Source"
        SOURCE_URL = "https://example.com/catalog.jsonl"
        RECORD_CLASS = MyRecord
"""

from __future__ import annotations

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)


class OLAuthor(BaseModel):
    name: str
    birth_date: Optional[str] = None
    death_date: Optional[str] = None


class OLImportRecord(BaseModel):
    """Mirrors openlibrary/schemata/import.schema.json (additionalProperties: false)."""

    model_config = ConfigDict(extra="forbid")

    # Required
    title: str
    source_records: List[str]
    authors: List[OLAuthor]
    publishers: List[str]
    publish_date: str

    # Optional bibliographic
    subtitle: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    edition_name: Optional[str] = None
    number_of_pages: Optional[int] = None
    pagination: Optional[str] = None
    by_statement: Optional[str] = None
    physical_format: Optional[str] = None
    physical_dimensions: Optional[str] = None
    weight: Optional[str] = None

    # Identifiers
    isbn_10: Optional[List[str]] = None
    isbn_13: Optional[List[str]] = None
    oclc_numbers: Optional[List[str]] = None
    lccn: Optional[List[str]] = None
    lc_classifications: Optional[List[str]] = None
    dewey_decimal_class: Optional[List[str]] = None
    identifiers: Optional[Dict[str, Any]] = None

    # Classification / subjects
    subjects: Optional[List[str]] = None
    subject_times: Optional[List[str]] = None
    subject_people: Optional[List[str]] = None
    subject_places: Optional[List[str]] = None

    # Language / translation
    languages: Optional[List[str]] = None
    translated_from: Optional[List[str]] = None
    translation_of: Optional[str] = None

    # Relations
    series: Optional[List[str]] = None
    contributions: Optional[List[str]] = None
    work_titles: Optional[List[str]] = None
    other_titles: Optional[List[str]] = None
    publish_places: Optional[List[str]] = None
    publish_country: Optional[str] = None

    # Media
    cover: Optional[str] = None
    links: Optional[List[Dict[str, Any]]] = None
    table_of_contents: Optional[List[Any]] = None


class DataProviderRecord(BaseModel, ABC):
    """
    Abstract base for one record in source-native form.

    Subclass with the source's fields as Pydantic attributes.
    Implement to_ol_import() to map them to OLImportRecord.
    Return None to skip the record (filtered out of the batch).

    extra='allow' so subclasses absorb unknown source fields (e.g. ebook_access)
    without validation errors.
    """

    model_config = ConfigDict(extra="allow")

    @abstractmethod
    def to_ol_import(self) -> Optional[OLImportRecord]:
        """Return None to exclude this record from the import batch."""
        ...


class DataProvider(ABC):
    """
    Abstract base for traversing a data source.

    Set SOURCE_SLUG and TITLE on the subclass; implement iter_records().
    """

    SOURCE_SLUG: str
    TITLE: str = "Unnamed Provider"

    @abstractmethod
    def iter_records(self) -> Iterator[DataProviderRecord]: ...

    def iter_ol_records(self) -> Iterator[OLImportRecord]:
        """Yield only non-None to_ol_import() results."""
        for record in self.iter_records():
            result = record.to_ol_import()
            if result is not None:
                yield result


class JSONLProvider(DataProvider, ABC):
    """
    Streams a JSONL file from a local path or remote URL.

    Set SOURCE_URL and RECORD_CLASS on the subclass.
    Malformed lines are logged and skipped.
    """

    SOURCE_URL: str
    RECORD_CLASS: type[DataProviderRecord]

    def iter_records(self) -> Iterator[DataProviderRecord]:
        with urllib.request.urlopen(self.SOURCE_URL) as f:
            for lineno, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    yield self.RECORD_CLASS.model_validate(data)
                except Exception as exc:
                    log.warning(
                        "%s: skipping line %d — %s", self.__class__.__name__, lineno, exc
                    )


class PaginatedAPIProvider(DataProvider, ABC):
    """
    Walks a paginated JSON REST API.

    Override iter_records() with API-specific pagination logic.
    """

    PAGE_SIZE: int = 100
