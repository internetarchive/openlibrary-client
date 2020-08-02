#-*- encoding: utf-8 -*-


import pytest
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

    def test__init__with_no_ol_arg(self):
        OpenLibrary = Mock()
        bot = BaseBot()
        assert OpenLibrary.assert_called_once()

# test__init__
# X calls ol when arg not given
# can parse --file, --limit, --dry-run from command line
# sets --dry-run and --limit when not set in command line
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


