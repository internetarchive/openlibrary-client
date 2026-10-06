"""Tests for the retype_tags entry point (pure logic, no network)."""

import unittest
from unittest.mock import Mock

from olclient.scripts.retype_tags import _parse_args, resolve_to_type, run


class TestResolveToType(unittest.TestCase):
    def test_explicit_to_type_wins(self):
        assert resolve_to_type('literary_form', 'something_else') == 'something_else'

    def test_defaults_to_known_plural(self):
        assert resolve_to_type('literary_form', None) == 'literary_forms'
        assert resolve_to_type('genre', None) == 'genres'
        assert resolve_to_type('audience', None) == 'audiences'

    def test_unknown_singular_without_explicit_is_none(self):
        assert resolve_to_type('mystery_type', None) is None


class TestRun(unittest.TestCase):
    def _mock_ol(self):
        ol = Mock()
        ol.Tag.retype.return_value = {
            'from_type': 'literary_form',
            'to_type': 'literary_forms',
            'dry_run': True,
            'to_retype': [{'olid': 'OL183T', 'name': 'Fiction'}],
            'retyped': [],
        }
        return ol

    def test_dry_run_is_the_default(self):
        args = _parse_args(['--from-type', 'literary_form'])
        assert args.write is False
        ol = self._mock_ol()
        run(args, ol=ol)
        _, kwargs = ol.Tag.retype.call_args
        assert kwargs['write'] is False

    def test_to_type_defaults_from_singular(self):
        args = _parse_args(['--from-type', 'genre'])
        ol = self._mock_ol()
        run(args, ol=ol)
        pos, _ = ol.Tag.retype.call_args
        assert pos[0] == 'genre'
        assert pos[1] == 'genres'  # derived default

    def test_write_flag_passes_through(self):
        args = _parse_args(['--from-type', 'genre', '--write'])
        ol = self._mock_ol()
        run(args, ol=ol)
        _, kwargs = ol.Tag.retype.call_args
        assert kwargs['write'] is True

    def test_aborts_when_no_to_type_resolvable(self):
        args = _parse_args(['--from-type', 'mystery_type'])
        ol = self._mock_ol()
        result = run(args, ol=ol)
        assert result is None
        ol.Tag.retype.assert_not_called()
