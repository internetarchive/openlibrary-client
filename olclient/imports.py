"""
imports.py
~~~~~~~~~~

Primitives for mapping external data sources to Open Library import records.

Architecture mirrors pyopds2 (https://github.com/ArchiveLabs/pyopds2):

    DataProvider      — knows how to traverse/iterate a source
    DataProviderRecord — Pydantic model of one source record; to_ol_import() converts it
    OLImportRecord    — Pydantic model mirroring olclient/schemata/import.schema.json

Concrete source implementations live in openlibrary-bots/sources/<slug>/.

Usage::

    class MyRecord(DataProviderRecord):
        title: str
        authors: list[dict]

        def to_ol_import(self):
            return OLImportRecord(
                title=self.title,
                source_records=["mysource:123"],
                authors=[OLAuthor(name=a["name"]) for a in self.authors],
                publishers=["Unknown"],
                publish_date="2024",
            )

    class MyProvider(JSONLProvider):
        SOURCE_SLUG = "mysource"
        SOURCE_URL = "https://example.com/data.jsonl"
        RECORD_CLASS = MyRecord

    for record in MyProvider().iter_ol_records():
        print(record.model_dump(exclude_none=True))
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from abc import ABC, abstractmethod
from typing import Iterator, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OL Import Record — mirrors import.schema.json
# ---------------------------------------------------------------------------


class OLLink(BaseModel):
    model_config = ConfigDict(extra='forbid')

    url: str
    title: str


class OLAuthor(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    personal_name: Optional[str] = None
    birth_date: Optional[str] = None
    death_date: Optional[str] = None
    entity_type: Optional[Literal["person", "org", "event"]] = None
    title: Optional[str] = None


class OLContributor(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    role: Optional[str] = None


class OLImportRecord(BaseModel):
    """
    Pydantic model mirroring olclient/schemata/import.schema.json.

    extra='forbid' enforces additionalProperties=false at the Python level,
    catching unknown fields before they reach the OL API (which silently drops them).
    """

    model_config = ConfigDict(extra='forbid')

    # Required
    title: str
    source_records: List[str]
    authors: List[OLAuthor]
    publishers: List[str]
    publish_date: str

    # Optional descriptive
    subtitle: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    edition_name: Optional[str] = None
    by_statement: Optional[str] = None

    # Optional publication
    publish_places: Optional[List[str]] = None
    publish_country: Optional[str] = None

    # Optional physical
    number_of_pages: Optional[int] = None
    pagination: Optional[str] = None
    physical_format: Optional[str] = None
    physical_dimensions: Optional[str] = None
    weight: Optional[str] = None

    # Optional classification
    lccn: Optional[List[str]] = None
    oclc_numbers: Optional[List[str]] = None
    isbn_10: Optional[List[str]] = None
    isbn_13: Optional[List[str]] = None
    lc_classifications: Optional[List[str]] = None
    dewey_decimal_class: Optional[List[str]] = None

    # Optional subjects
    subjects: Optional[List[str]] = None
    subject_times: Optional[List[str]] = None
    subject_people: Optional[List[str]] = None
    subject_places: Optional[List[str]] = None

    # Optional language
    languages: Optional[List[str]] = None
    translated_from: Optional[List[str]] = None
    translation_of: Optional[str] = None

    # Optional relations
    series: Optional[List[str]] = None
    contributions: Optional[List[str]] = None
    work_titles: Optional[List[str]] = None
    other_titles: Optional[List[str]] = None
    contributor: Optional[List[OLContributor]] = None
    table_of_contents: Optional[list] = None

    # Optional links / cover
    links: Optional[List[OLLink]] = None
    cover: Optional[str] = None  # URL for edition's cover image

    # Optional identifiers (external site IDs; values are lists per schema)
    identifiers: Optional[dict[str, List[str]]] = None

    @field_validator('identifiers')
    @classmethod
    def _validate_identifier_keys(cls, v: Optional[dict]) -> Optional[dict]:
        if v:
            for key in v:
                if not re.match(r'^\w+$', key):
                    raise ValueError(
                        f"Identifier key {key!r} must match ^\\w+ (letters, digits, underscores only)"
                    )
        return v


# ---------------------------------------------------------------------------
# DataProviderRecord — abstract base for one source-native record
# ---------------------------------------------------------------------------


class DataProviderRecord(BaseModel, ABC):
    """
    Abstract base for one record modelled in the source's native schema.

    Subclass with Pydantic fields matching the raw source data, then implement
    to_ol_import() to convert to OLImportRecord. Return None to skip the record.

    extra='allow' because source schemas vary and we only extract what we need.
    """

    model_config = ConfigDict(extra='allow')

    @abstractmethod
    def to_ol_import(self) -> Optional[OLImportRecord]:
        """Return an OLImportRecord, or None to exclude this record from the batch."""
        ...


# ---------------------------------------------------------------------------
# DataProvider — abstract base for traversing a source
# ---------------------------------------------------------------------------


class DataProvider(ABC):
    """
    Abstract base for traversing a data source.

    Class attributes:
        SOURCE_SLUG  stable prefix for source_records field (e.g. "itan", "bwb")
        TITLE        human-readable name for this source

    Implement iter_records() with your traversal strategy (file, API, feed, S3, …).
    """

    SOURCE_SLUG: str
    TITLE: str = "Unnamed Provider"

    @abstractmethod
    def iter_records(self) -> Iterator[DataProviderRecord]:
        """Yield all records from the source in source-native form."""
        ...

    def iter_ol_records(self) -> Iterator[OLImportRecord]:
        """Yield OLImportRecords, skipping records where to_ol_import() returns None."""
        for record in self.iter_records():
            result = record.to_ol_import()
            if result is not None:
                yield result


# ---------------------------------------------------------------------------
# JSONLProvider — mixin for JSONL file sources (local path or remote URL)
# ---------------------------------------------------------------------------


class JSONLProvider(DataProvider, ABC):
    """
    Streams a JSONL file from a local filesystem path or a remote URL.

    Subclasses must define:
        SOURCE_URL    local path or http(s) URL
        RECORD_CLASS  the DataProviderRecord subclass to validate each line into

    Lines that fail JSON parsing or Pydantic validation are skipped with a warning.
    """

    SOURCE_URL: str
    RECORD_CLASS: type[DataProviderRecord]

    def iter_records(self) -> Iterator[DataProviderRecord]:
        if self.SOURCE_URL.startswith(('http://', 'https://')):
            yield from self._iter_remote(self.SOURCE_URL)
        else:
            yield from self._iter_local(self.SOURCE_URL)

    TIMEOUT: int = 30  # seconds; override on subclass for slow sources

    def _iter_remote(self, url: str) -> Iterator[DataProviderRecord]:
        with urllib.request.urlopen(url, timeout=self.TIMEOUT) as f:
            for lineno, raw in enumerate(f, 1):
                yield from self._parse_line(raw, lineno)

    def _iter_local(self, path: str) -> Iterator[DataProviderRecord]:
        with open(path, 'rb') as f:
            for lineno, raw in enumerate(f, 1):
                yield from self._parse_line(raw, lineno)

    def _parse_line(self, raw: bytes, lineno: int) -> Iterator[DataProviderRecord]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("Line %d: JSON parse error — %s", lineno, exc)
            return
        try:
            yield self.RECORD_CLASS.model_validate(data)
        except ValidationError as exc:
            log.warning("Line %d: validation error — %s", lineno, exc)


# ---------------------------------------------------------------------------
# PaginatedAPIProvider — base for paginated REST API sources
# ---------------------------------------------------------------------------


class PaginatedAPIProvider(DataProvider, ABC):
    """
    Skeleton for paginated JSON REST APIs.

    PAGE_SIZE is a convention; subclasses manage their own pagination loop inside
    iter_records(). See JSONLProvider for a complete mixin example.
    """

    PAGE_SIZE: int = 100
