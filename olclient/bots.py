#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
Classes and methods for bulk edits that match the following pattern:
1. Search data dump for X condition
2. Remove or modify record that fit s condition X
3. Create log of modification
4. Repeat 1-3 for all records that meet condition X
"""


import argparse
import datetime
import logging
import sys

from olclient.openlibrary import OpenLibrary
from os import makedirs, path


class BaseBot(object):
    def __init__(self, ol=None, dry_run=True, limit=1) -> None:
        """Create logger and class variables"""
        self.ol = ol or OpenLibrary()

        self.parser = argparse.ArgumentParser(description=__doc__)
        self.parser.add_argument('-f', '--file', type=str, default=None, help='Path to file containing input data')
        self.parser.add_argument('-l, --limit', type=int, default=1,
                                 help='Limit number of edits performed on external data.'
                                      'Set to zero to allow unlimited edits.')
        self.parser.add_argument('-d', '--dry-run', type=self._str2bool, default=True,
                                 help='Execute the script without performing edits on external data.')
        self.args = self.parser.parse_args()
        self.dry_run = getattr(self.args, 'dry-run', None) or dry_run
        self.limit = getattr(self.args, 'limit', None) or limit
        self.changed = 0

        job_name = path.splitext(sys.argv[0])[0]
        if '/' or '\\' in job_name:  # FIXME: this is disgusting and path.isfile() and path.isdir() don't work
            job_name = path.splitext(job_name)[-1] or 'a_girl_has_no_name'
        self.logger = logging.getLogger("jobs.%s" % job_name)
        self.logger.setLevel(logging.DEBUG)
        log_formatter = logging.Formatter('%(name)s;%(levelname)-8s;%(asctime)s %(message)s')
        self.console_handler = logging.StreamHandler()
        self.console_handler.setLevel(logging.WARN)
        self.console_handler.setFormatter(log_formatter)
        self.logger.addHandler(self.console_handler)
        home = path.expanduser("~")
        log_dir = ''.join([home, '/logs/jobs/', job_name])
        makedirs(log_dir, exist_ok=True)
        log_file_datetime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir + '/%s_%s.log' % (job_name, log_file_datetime)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_formatter)
        self.logger.addHandler(file_handler)
        self.console_handler.setLevel(logging.INFO)

    @staticmethod
    def _str2bool(value: str) -> bool:
        """
        Convert sensible input strings into booleans. Unacceptable strings raise an error.
        :param value: User input
        """
        if isinstance(value, bool):
            return value
        if value.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif value.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    def run(self) -> None:
        """You should overwrite this method"""
        self.logger.debug('run method is not defined. Exiting script.')
        sys.exit()

    def save(self, save_fn) -> None:
        """
        Modify behavior of OpenLibrary Client based on 'limit' and 'dry_run' parameters
        :param save_fn: Save function of an OpenLibrary Client record (Work, Edition, Author)
        """
        if not self.dry_run:
            save_fn()
        else:
            self.logger.info('Modification not made because dry_run is True.')
        self.changed += 1
        if self.limit and self.changed >= self.limit:
            self.logger.info('Modification limit reached. Exiting script.')
            sys.exit()
