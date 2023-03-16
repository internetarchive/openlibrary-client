import copy
import logging
import random
import string
import sys
import unittest

from argparse import ArgumentTypeError
from olclient.openlibrary import OpenLibrary
from olclient.bots import AbstractBotJob
from os import path
from unittest.mock import MagicMock, Mock, call, patch, ANY


@patch('olclient.openlibrary.OpenLibrary.login')
class TestBots(unittest.TestCase):
    def setUp(self):
        self.truthy_values = ['yes', 'true', 't', 'y', '1']
        self.falsey_values = ['no', 'false', 'f', 'n', '0']
        # clear pytest args from being passed to AbstractBotJob()
        sys.argv = [sys.argv[0]]

    def test__init__(self, mock_login):
        bot = AbstractBotJob()
        assert bot.changed == 0
        assert bot.limit == 1
        assert bot.write_changes is False
        assert bot.logger.handlers
        assert getattr(bot, 'console_handler', None) is not None
        assert isinstance(bot.ol, OpenLibrary)

    def test__str2bool_returns_true_for_truthy_input(self, mock_login):
        truthy_input = random.choice(self.truthy_values)
        bot = AbstractBotJob()
        assert bot._str2bool(truthy_input)

    def test__str2bool_returns_false_for_falsey_input(self, mock_login):
        falsey_input = random.choice(self.falsey_values)
        bot = AbstractBotJob()
        assert bot._str2bool(falsey_input) is False

    def test__str2bool_errors_for_non_boolean_input(self, mock_login):
        bot = AbstractBotJob()
        self.assertRaises(
            ArgumentTypeError, bot._str2bool, 'this is a non-boolean string'
        )

    def test_write_changes_declaration_when_write_changes_is_true(self, mock_login):
        bot = AbstractBotJob(write_changes=True)
        bot.logger.info = Mock()
        bot.write_changes_declaration()
        bot.logger.info.assert_called_with(
            'write_changes is TRUE. Permanent modifications may be made.'
        )  # TODO

    def test_write_changes_declaration_when_write_changes_is_false(self, mock_login):
        bot = AbstractBotJob(write_changes=False)
        bot.logger.info = Mock()
        bot.write_changes_declaration()
        bot.logger.info.assert_called_with(
            'write_changes is FALSE. No external modifications will be made.'
        )  # TODO

    def test_process_row_with_bytecode(self, mock_login):
        random_data = [random.choice(string.ascii_letters) for _ in range(4)]
        random_data = '\t'.join(
            [
                random_data[0],
                random_data[1],
                random_data[2],
                random_data[3],
                '{"foo": "bar" }',
            ]
        )
        random_byte_data = random_data.encode()
        job = AbstractBotJob()
        returned_row, returned_json_data = job.process_row(random_byte_data)
        assert isinstance(returned_row, list)
        assert isinstance(returned_json_data, dict)

    def test_process_row_with_string(self, mock_login):
        random_data = [random.choice(string.ascii_letters) for _ in range(4)]
        random_data = '\t'.join(
            [
                random_data[0],
                random_data[1],
                random_data[2],
                random_data[3],
                '{"foo": "bar" }',
            ]
        )
        job = AbstractBotJob()
        returned_row, returned_json_data = job.process_row(random_data)
        assert isinstance(returned_row, list)
        assert isinstance(returned_json_data, dict)

    @patch('olclient.bots.sys.exit')
    def test_save_exits_when_limit_reached(self, mock_login, mock_sys_exit):
        save_fn = Mock()
        bot = AbstractBotJob(write_changes=False, limit=10)
        bot.logger.info = Mock()
        # simulate calling save_fn many times in a run() method
        for i in range(bot.limit):
            if mock_sys_exit.call_count > 1:
                break
            bot.save(save_fn)
        assert mock_sys_exit.assert_called_once
        assert save_fn.assert_not_called
        assert bot.changed == bot.limit
        assert bot.logger.info.call_count == bot.limit + 1

    @patch('olclient.bots.sys.exit')
    def test_save_when_write_changes_is_true(self, mock_login, mock_sys_exit):
        save_fn = Mock()
        bot = AbstractBotJob(write_changes=True)
        bot.logger.info = Mock()
        old_changed = copy.deepcopy(bot.changed)
        bot.save(save_fn)
        assert save_fn.assert_called_once
        assert bot.logger.info.assert_called_once
        assert mock_sys_exit.assert_called_once
        assert bot.changed == old_changed + 1
        assert not bot.changed > bot.limit

    @patch('olclient.bots.sys.exit')
    def test_save_when_write_changes_is_false(self, mock_login, mock_sys_exit):
        save_fn = Mock()
        bot = AbstractBotJob(write_changes=False)
        bot.logger.info = Mock()
        old_changed = copy.deepcopy(bot.changed)
        bot.save(save_fn)
        assert save_fn.assert_not_called
        assert bot.logger.info.call_count == 2
        assert mock_sys_exit.assert_called_once
        assert bot.changed == old_changed + 1
        assert not bot.changed > bot.limit

    def test_setup_logger(self, mock_login):
        job_name = __name__
        logger, console_handler = AbstractBotJob.setup_logger(job_name)
        assert isinstance(logger, logging.Logger)
        assert isinstance(console_handler, logging.StreamHandler)
