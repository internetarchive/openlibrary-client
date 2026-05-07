"""
Tests for olclient/imports.py

Coverage:
- OLImportRecord: required fields, extra-field rejection, optional fields, nested models
- OLAuthor / OLContributor / OLLink: field validation
- DataProviderRecord: concrete subclass, to_ol_import(), skip-via-None
- DataProvider: iter_ol_records() filters None results
- JSONLProvider: local JSONL file, bad lines skipped, remote URL path exists
- Cross-validation: OLImportRecord output validates against import.schema.json
"""

import json
import os
import tempfile
from nturl2path import pathname2url
from typing import Iterator, Optional

import jsonschema
import pytest
from pydantic import ValidationError

from olclient.imports import (
    DataProvider,
    DataProviderRecord,
    JSONLProvider,
    OLAuthor,
    OLContributor,
    OLImportRecord,
    OLLink,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'olclient', 'schemata', 'import.schema.json'
)

with open(SCHEMA_PATH) as _f:
    _IMPORT_SCHEMA = json.load(_f)

_RESOLVER = jsonschema.RefResolver('file:' + pathname2url(os.path.abspath(SCHEMA_PATH)), _IMPORT_SCHEMA)
_VALIDATOR = jsonschema.Draft4Validator(_IMPORT_SCHEMA, resolver=_RESOLVER)


def assert_valid_schema(record: OLImportRecord) -> None:
    """Assert that a record's dict form passes the canonical JSON schema."""
    data = record.model_dump(exclude_none=True)
    errors = list(_VALIDATOR.iter_errors(data))
    assert not errors, f"Schema validation errors: {errors}"


def minimal_record(**overrides) -> dict:
    """Return the minimum valid kwargs for OLImportRecord."""
    base = {
        "title": "Test Book",
        "source_records": ["test:001"],
        "authors": [{"name": "Author One"}],
        "publishers": ["Test Press"],
        "publish_date": "2024",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# OLAuthor
# ---------------------------------------------------------------------------


class TestOLAuthor:
    def test_name_only(self):
        a = OLAuthor(name="Joan Miró")
        assert a.name == "Joan Miró"

    def test_all_fields(self):
        a = OLAuthor(
            name="Hardy, G. H.",
            personal_name="Hardy, G. H.",
            birth_date="1877",
            death_date="1947",
            entity_type="person",
            title="Prof.",
        )
        assert a.entity_type == "person"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            OLAuthor(name="X", unknown_field="bad")


# ---------------------------------------------------------------------------
# OLContributor
# ---------------------------------------------------------------------------


class TestOLContributor:
    def test_name_and_role(self):
        c = OLContributor(name="Jane Smith", role="Editor")
        assert c.role == "Editor"

    def test_name_only(self):
        c = OLContributor(name="Jane Smith")
        assert c.role is None

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            OLContributor(name="X", extra="bad")


# ---------------------------------------------------------------------------
# OLLink
# ---------------------------------------------------------------------------


class TestOLLink:
    def test_valid(self):
        link = OLLink(url="https://example.com", title="Homepage")
        assert link.url == "https://example.com"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            OLLink(url="https://example.com", title="X", rel="alternate")


# ---------------------------------------------------------------------------
# OLImportRecord — construction
# ---------------------------------------------------------------------------


class TestOLImportRecord:
    def test_minimal_valid(self):
        r = OLImportRecord(**minimal_record())
        assert r.title == "Test Book"
        assert r.subtitle is None

    def test_rejects_missing_title(self):
        kwargs = minimal_record()
        del kwargs["title"]
        with pytest.raises(ValidationError):
            OLImportRecord(**kwargs)

    def test_rejects_missing_authors(self):
        kwargs = minimal_record()
        del kwargs["authors"]
        with pytest.raises(ValidationError):
            OLImportRecord(**kwargs)

    def test_rejects_missing_publishers(self):
        kwargs = minimal_record()
        del kwargs["publishers"]
        with pytest.raises(ValidationError):
            OLImportRecord(**kwargs)

    def test_rejects_missing_publish_date(self):
        kwargs = minimal_record()
        del kwargs["publish_date"]
        with pytest.raises(ValidationError):
            OLImportRecord(**kwargs)

    def test_rejects_missing_source_records(self):
        kwargs = minimal_record()
        del kwargs["source_records"]
        with pytest.raises(ValidationError):
            OLImportRecord(**kwargs)

    def test_rejects_extra_field(self):
        with pytest.raises(ValidationError):
            OLImportRecord(**minimal_record(), cover_url="https://example.com/img.jpg")

    def test_cover_field_name_is_cover_not_cover_url(self):
        r = OLImportRecord(**minimal_record(), cover="https://example.com/img.jpg")
        assert r.cover == "https://example.com/img.jpg"

    def test_identifiers_values_are_lists(self):
        r = OLImportRecord(
            **minimal_record(),
            identifiers={"itan_id": ["ISIN123"]},
        )
        assert r.identifiers["itan_id"] == ["ISIN123"]

    def test_full_optional_fields(self):
        r = OLImportRecord(
            **minimal_record(),
            subtitle="A Subtitle",
            isbn_13=["9780441569595"],
            languages=["eng"],
            subjects=["Fiction", "Science Fiction"],
            series=["Sprawl Trilogy"],
            contributor=[{"name": "Ed Smith", "role": "Editor"}],
            links=[{"url": "https://example.com", "title": "Homepage"}],
            identifiers={"goodreads": ["12345"]},
            cover="https://covers.example.com/book.jpg",
        )
        assert r.subtitle == "A Subtitle"
        assert r.isbn_13 == ["9780441569595"]
        assert r.contributor[0].role == "Editor"

    def test_model_dump_excludes_none(self):
        r = OLImportRecord(**minimal_record())
        dumped = r.model_dump(exclude_none=True)
        assert "subtitle" not in dumped
        assert "title" in dumped


# ---------------------------------------------------------------------------
# OLImportRecord — cross-validation against canonical JSON schema
# ---------------------------------------------------------------------------


class TestOLImportRecordSchema:
    def test_minimal_passes_json_schema(self):
        r = OLImportRecord(**minimal_record())
        assert_valid_schema(r)

    def test_full_record_passes_json_schema(self):
        r = OLImportRecord(
            title="Neuromancer",
            source_records=["test:neuromancer"],
            authors=[OLAuthor(name="Gibson, William", birth_date="1948", entity_type="person")],
            publishers=["Ace Books"],
            publish_date="1984",
            isbn_10=["0441569595"],
            isbn_13=["9780441569595"],
            lccn=["91174394"],
            languages=["eng"],
            subjects=["Science fiction"],
            cover="https://covers.openlibrary.org/b/id/1234-L.jpg",
        )
        assert_valid_schema(r)

    def test_identifiers_pass_json_schema(self):
        r = OLImportRecord(
            **minimal_record(),
            identifiers={"itan_id": ["ISIN001"], "project_gutenberg": ["64317"]},
        )
        assert_valid_schema(r)


# ---------------------------------------------------------------------------
# DataProviderRecord — concrete subclass
# ---------------------------------------------------------------------------


class _SampleRecord(DataProviderRecord):
    """Minimal concrete record for testing."""

    isin: str
    title: str
    author_name: str
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    should_skip: bool = False

    def to_ol_import(self) -> Optional[OLImportRecord]:
        if self.should_skip:
            return None
        return OLImportRecord(
            title=self.title,
            source_records=[f"test:{self.isin}"],
            authors=[OLAuthor(name=self.author_name)],
            publishers=[self.publisher or "Unknown"],
            publish_date=self.publish_date or "2024",
        )


class TestDataProviderRecord:
    def test_to_ol_import_returns_record(self):
        rec = _SampleRecord(isin="001", title="Book A", author_name="Alice")
        result = rec.to_ol_import()
        assert isinstance(result, OLImportRecord)
        assert result.title == "Book A"
        assert result.source_records == ["test:001"]

    def test_to_ol_import_returns_none_to_skip(self):
        rec = _SampleRecord(isin="002", title="Junk", author_name="X", should_skip=True)
        assert rec.to_ol_import() is None

    def test_extra_source_fields_are_allowed(self):
        # DataProviderRecord uses extra='allow' — source fields beyond the model are fine
        rec = _SampleRecord(isin="003", title="T", author_name="A", unknown_field="ok")
        assert rec.to_ol_import() is not None

    def test_output_passes_json_schema(self):
        rec = _SampleRecord(isin="004", title="Valid", author_name="Author", publish_date="2023")
        assert_valid_schema(rec.to_ol_import())


# ---------------------------------------------------------------------------
# DataProvider — concrete subclass and iter_ol_records
# ---------------------------------------------------------------------------


class _SampleProvider(DataProvider):
    SOURCE_SLUG = "test"
    TITLE = "Test Provider"

    def __init__(self, records):
        self._records = records

    def iter_records(self) -> Iterator[DataProviderRecord]:
        yield from self._records


class TestDataProvider:
    def _make_records(self, n_good=3, n_skip=2):
        good = [_SampleRecord(isin=f"G{i}", title=f"Good {i}", author_name="A") for i in range(n_good)]
        skip = [_SampleRecord(isin=f"S{i}", title=f"Skip {i}", author_name="A", should_skip=True) for i in range(n_skip)]
        return good + skip

    def test_iter_records_yields_all(self):
        provider = _SampleProvider(self._make_records(3, 2))
        assert sum(1 for _ in provider.iter_records()) == 5

    def test_iter_ol_records_filters_none(self):
        provider = _SampleProvider(self._make_records(3, 2))
        results = list(provider.iter_ol_records())
        assert len(results) == 3
        assert all(isinstance(r, OLImportRecord) for r in results)

    def test_iter_ol_records_empty_source(self):
        provider = _SampleProvider([])
        assert list(provider.iter_ol_records()) == []


# ---------------------------------------------------------------------------
# JSONLProvider — local file
# ---------------------------------------------------------------------------


class _TestJSONLRecord(DataProviderRecord):
    id: str
    title: str
    author: str

    def to_ol_import(self) -> Optional[OLImportRecord]:
        if not self.title:
            return None
        return OLImportRecord(
            title=self.title,
            source_records=[f"jsonltest:{self.id}"],
            authors=[OLAuthor(name=self.author)],
            publishers=["JSONL Press"],
            publish_date="2025",
        )


class _TestJSONLProvider(JSONLProvider):
    SOURCE_SLUG = "jsonltest"
    RECORD_CLASS = _TestJSONLRecord

    def __init__(self, path: str):
        self.SOURCE_URL = path


class TestJSONLProvider:
    def _write_jsonl(self, lines: list) -> str:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        for line in lines:
            f.write(json.dumps(line) + '\n')
        f.close()
        return f.name

    def test_reads_valid_jsonl(self, tmp_path):
        path = str(tmp_path / "data.jsonl")
        records = [
            {"id": "1", "title": "Book One", "author": "Alice"},
            {"id": "2", "title": "Book Two", "author": "Bob"},
        ]
        with open(path, 'w') as f:
            for r in records:
                f.write(json.dumps(r) + '\n')

        provider = _TestJSONLProvider(path)
        results = list(provider.iter_ol_records())
        assert len(results) == 2
        assert results[0].title == "Book One"
        assert results[1].source_records == ["jsonltest:2"]

    def test_skips_bad_json_lines(self, tmp_path, caplog):
        import logging
        path = str(tmp_path / "bad.jsonl")
        with open(path, 'w') as f:
            f.write('{"id": "1", "title": "Good", "author": "A"}\n')
            f.write('NOT JSON\n')
            f.write('{"id": "3", "title": "Also Good", "author": "B"}\n')

        provider = _TestJSONLProvider(path)
        with caplog.at_level(logging.WARNING, logger="olclient.imports"):
            results = list(provider.iter_ol_records())

        assert len(results) == 2
        assert any("JSON parse error" in m for m in caplog.messages)

    def test_skips_lines_failing_validation(self, tmp_path, caplog):
        import logging
        path = str(tmp_path / "invalid.jsonl")
        with open(path, 'w') as f:
            f.write('{"id": "1", "title": "Good", "author": "A"}\n')
            # Missing required 'title' and 'author' fields for _TestJSONLRecord
            f.write('{"id": "2"}\n')

        provider = _TestJSONLProvider(path)
        with caplog.at_level(logging.WARNING, logger="olclient.imports"):
            results = list(provider.iter_ol_records())

        assert len(results) == 1
        assert any("validation error" in m for m in caplog.messages)

    def test_empty_file(self, tmp_path):
        path_obj = tmp_path / "empty.jsonl"
        path_obj.write_text("")
        provider = _TestJSONLProvider(str(path_obj))
        assert list(provider.iter_ol_records()) == []

    def test_output_passes_json_schema(self, tmp_path):
        path = tmp_path / "schema_check.jsonl"
        path.write_text(json.dumps({"id": "99", "title": "Schema Test", "author": "Tester"}) + "\n")
        provider = _TestJSONLProvider(str(path))
        for record in provider.iter_ol_records():
            assert_valid_schema(record)
