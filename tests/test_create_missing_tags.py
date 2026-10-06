"""Tests for the create_missing_tags entry point (pure logic, no network)."""

import json
import unittest
from unittest.mock import Mock

from olclient.scripts.create_missing_tags import (
    _parse_args,
    load_vocabulary,
    run,
)


def _write_vocab(tmpdir, type_name, tags):
    path = tmpdir / 'vocabulary.json'
    path.write_text(json.dumps({'type': type_name, 'tags': tags}))
    return str(path)


class TestLoadVocabulary(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_maps_tags_repo_fields_to_canonical(self):
        path = _write_vocab(
            self.tmp,
            'content_formats',
            [
                {
                    'tag': 'Almanac',
                    'slug': 'almanac',
                    'definition': 'Annual reference',
                    'key': '/tags/OL120T',
                },
                {'tag': 'Zine', 'slug': 'zine', 'definition': 'Small-run booklet'},
            ],
        )
        declared, terms = load_vocabulary(path)
        assert declared == 'content_formats'
        assert terms[0] == {
            'name': 'Almanac',
            'slug': 'almanac',
            'description': 'Annual reference',
            'key': '/tags/OL120T',
        }
        # entry without a key carries no 'key' (so it's eligible for creation)
        assert 'key' not in terms[1]
        assert terms[1]['name'] == 'Zine'

    def test_singular_declared_type_is_returned_as_is(self):
        # literary_form/ is singular in the source; load does not "fix" it.
        path = _write_vocab(self.tmp, 'literary_form', [{'tag': 'Fiction'}])
        declared, terms = load_vocabulary(path)
        assert declared == 'literary_form'


class TestRun(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _mock_ol(self):
        ol = Mock()
        ol.Tag.create_missing.return_value = {
            'tag_type': 'literary_forms',
            'dry_run': True,
            'to_create': ['Nonfiction'],
            'created': [],
            'skipped_existing': ['Fiction'],
            'skipped_has_key': [],
        }
        return ol

    def test_dry_run_is_the_default(self):
        path = _write_vocab(self.tmp, 'literary_forms', [{'tag': 'Fiction'}])
        args = _parse_args([path, '--tag-type', 'literary_forms'])
        assert args.write is False
        ol = self._mock_ol()
        run(args, ol=ol)
        # create_missing is called with write=False on a dry-run
        _, kwargs = ol.Tag.create_missing.call_args
        assert kwargs['write'] is False

    def test_write_flag_passes_through(self):
        path = _write_vocab(self.tmp, 'literary_forms', [{'tag': 'Fiction'}])
        args = _parse_args([path, '--tag-type', 'literary_forms', '--write'])
        ol = self._mock_ol()
        run(args, ol=ol)
        _, kwargs = ol.Tag.create_missing.call_args
        assert kwargs['write'] is True

    def test_explicit_tag_type_overrides_singular_file_type(self):
        # Source dir/type is singular 'literary_form'; we target plural.
        path = _write_vocab(self.tmp, 'literary_form', [{'tag': 'Fiction'}])
        args = _parse_args([path, '--tag-type', 'literary_forms'])
        ol = self._mock_ol()
        run(args, ol=ol)
        pos, _ = ol.Tag.create_missing.call_args
        assert pos[0] == 'literary_forms'  # the explicit flag, not the file

    def test_warns_on_type_mismatch(self):
        path = _write_vocab(self.tmp, 'literary_form', [{'tag': 'Fiction'}])
        args = _parse_args([path, '--tag-type', 'literary_forms'])
        from io import StringIO
        import contextlib

        err = StringIO()
        with contextlib.redirect_stderr(err):
            run(args, ol=self._mock_ol())
        assert 'WARNING' in err.getvalue()
        assert "'literary_form'" in err.getvalue()

    def test_no_warning_when_types_match(self):
        path = _write_vocab(self.tmp, 'literary_forms', [{'tag': 'Fiction'}])
        args = _parse_args([path, '--tag-type', 'literary_forms'])
        from io import StringIO
        import contextlib

        err = StringIO()
        with contextlib.redirect_stderr(err):
            run(args, ol=self._mock_ol())
        assert err.getvalue() == ''
