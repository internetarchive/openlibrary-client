#-*- encoding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import copy
import random
import string
import unittest

try:
    from mock import MagicMock, Mock, call, patch, ANY
except ImportError:
    from unittest.mock import MagicMock, Mock, call, patch, ANY

from argparse import ArgumentTypeError
from olclient.openlibrary import OpenLibrary
from olclient.bots import BaseBot


class TestBots(unittest.TestCase):

    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()
        self.truthy_values = ['yes', 'true',  't', 'y', '1']
        self.falsey_values = ['no', 'false', 'f', 'n', '0']

    def test__init__(self):
        bot = BaseBot()
        assert bot.changed == 0
        assert bot.limit == 1
        assert bot.logger.handlers
        assert isinstance(bot.ol, OpenLibrary)

    def test__str2bool_returns_true_for_truthy_input(self):
        truthy_input = self.truthy_values[random.randint(0, len(self.truthy_values) - 1)]
        bot = BaseBot(ol=self.ol)
        assert bot._str2bool(truthy_input)

    def test__str2bool_returns_false_for_falsey_input(self):
        falsey_input = self.falsey_values[random.randint(0, len(self.falsey_values) - 1)]
        bot = BaseBot(ol=self.ol)
        assert bot._str2bool(falsey_input) is False

    def test__str2bool_errors_for_non_boolean_input(self):
        non_boolean_input = random.choice(string.ascii_letters)
        while non_boolean_input in self.falsey_values or non_boolean_input in self.truthy_values:
            non_boolean_input = random.choice(string.ascii_letters)
        bot = BaseBot(ol=self.ol)
        self.assertRaises(ArgumentTypeError, bot._str2bool, non_boolean_input)

    @patch('olclient.bots.sys.exit')  # so that pytest doesn't exit
    def test_save_when_dry_run_is_false(self, mock_sys_exit):
        save_fn = Mock()
        bot = BaseBot(ol=self.ol, dry_run=False)
        old_changed = copy.deepcopy(bot.changed)
        bot.save(save_fn)
        assert save_fn.assert_called_once()
        assert bot.changed == old_changed + 1
        assert not bot.changed > bot.limit

    @patch('olclient.bots.sys.exit')  # so that pytest doesn't exit
    def test_save_when_dry_run_is_true(self, mock_sys_exit):
        save_fn = Mock()
        bot = BaseBot(ol=self.ol, dry_run=True)
        old_changed = copy.deepcopy(bot.changed)
        bot.save(save_fn)
        assert save_fn.assert_not_called()
        assert bot.changed == old_changed + 1
        assert not bot.changed > bot.limit
