#-*- encoding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import random
import sys
import unittest

try:
    from mock import Mock, call, patch, ANY
except ImportError:
    from unittest.mock import Mock, call, patch, ANY

from olclient.openlibrary import OpenLibrary
from olclient.bots import BaseBot


class TestBots(unittest.TestCase):

    @patch('olclient.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    @patch('olclient.openlibrary.OpenLibrary')
    def test__init__(self, mock_ol):
        bot = BaseBot()
        assert bot.dry_run
        assert bot.limit == 1
        assert bot.logger.handlers
        assert mock_ol.assert_called_once()  # FIXME not passing for some reason

    @patch('olclient.bots.logging.debug')
    @patch('olclient.bots.sys.exit')
    def test_run(self, mock_debug, mock_sys_exit):
        bot = BaseBot()
        assert mock_sys_exit.assert_called_once()  # FIXME not passing for some reason
        assert mock_debug.assert_called_once()  # FIXME not passing for some reason


# test__init__
# X calls ol when arg not given
# can parse --file, --limit, --dry-run from command line
# X sets --dry-run and --limit when not set in command line
# creates log file and directory

# def_run
# calls debug, calls exit

# test_save
# calls save_fn when --dry-run=False, change increases by 1
# does not call save_fun when --dry_run=True, changed increase by 1
# adds to log file when limit reached

# test_str2bool
# randomly pick 'yes', 'true', 't', 'y', '1' and make sure it returns True
# randomly pick 'no', 'false', 'f', 'n', '0' and make sure it returns False
# assert ArgumentTypeError raised for bad choice


