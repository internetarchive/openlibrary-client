"""
Classes and methods for bulk edits that match the following pattern:
1. Search data dump for X condition
2. Remove or modify record that fits condition X
3. Create log of modification
4. Repeat 1-3 for all records that meet condition X
"""


import argparse
import datetime
import json
import logging
import sys

from typing import Tuple
from olclient.openlibrary import OpenLibrary
from os import makedirs, path


class AbstractBotJob:
    def __init__(self, ol=None, write_changes=False, limit=1, job_name=__name__) -> None:
        """Create logger and class variables"""
        self.ol = ol or OpenLibrary()

        self.parser = argparse.ArgumentParser(description=__doc__)
        self.parser.add_argument(
            '-f',
            '--file',
            type=str,
            default=None,
            help='Path to file containing input data',
        )
        self.parser.add_argument(
            '-l',
            '--limit',
            type=int,
            default=1,
            help='Limit number of edits performed on external data.'
            'Set to zero to allow unlimited edits.',
        )
        self.parser.add_argument(
            '-w',
            '--write-changes',
            action="store_true",
            help='Execute the script and write all changes to external data.',
        )
        self.args = self.parser.parse_args()
        self.write_changes = write_changes or self.args.write_changes 
        self.limit = getattr(self.args, 'limit', None) or limit
        self.changed = 0

        self.logger, self.console_handler = self.setup_logger(job_name)

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

    def write_changes_declaration(self) -> None:
        """Log whether write_changes is True or False"""
        if self.write_changes:
            self.logger.info('write_changes is TRUE. Permanent modifications may be made.')
        else:
            self.logger.info('write_changes is FALSE. No external modifications will be made.')
    def dry_run_declaration(self):
        self.write_changes_declaration()
    @staticmethod
    def process_row(row, delimiter='\t') -> Tuple[list, dict]:
        """
        Return one row and accompanying JSON of an Open Library dump into useful data formats
        I.E:
        with open(self.args.file) as file:
            for row in file:
                row, json_data = self.process_row(row)

        :param row: One row of a compressed or plain text file
        :param delimiter: The delimiter of the text file. Default is \t
        :returns: A tuple. first element is the row and the second element is the JSON data
        """
        try:
            row = row.decode().split(delimiter)
        except AttributeError:
            row = row.split(delimiter)
        return row, json.loads(row[4])

    def run(self) -> None:
        """You should overwrite this method"""
        self.logger.debug('run method is not defined. Exiting script.')
        sys.exit()

    def save(self, save_fn) -> None:
        """
        Modify behavior of OpenLibrary Client based on 'limit' and 'write_changes' parameters
        :param save_fn: Save function of an OpenLibrary Client record (Work, Edition, Author)
        """
        if self.write_changes:
            save_fn()
        else:
            self.logger.info('Modification not made because write_changes is False.')
        self.changed += 1
        if self.limit and self.changed >= self.limit:
            self.logger.info('Modification limit reached. Exiting script.')
            sys.exit()

    @staticmethod
    def setup_logger(job_name: str) -> tuple:
        """
        :param job_name: The name that will appear on the log files
        :returns: a tuple of the logger instance and the console handler instance
        """
        logger = logging.getLogger("jobs.%s" % job_name)
        logger.setLevel(logging.DEBUG)
        log_formatter = logging.Formatter(
            '%(name)s;%(levelname)-8s;%(asctime)s %(message)s'
        )
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARN)
        console_handler.setFormatter(log_formatter)
        logger.addHandler(console_handler)
        here = path.dirname(path.abspath(__name__))
        log_dir = path.join(here, 'logs', 'jobs', job_name)
        makedirs(log_dir, exist_ok=True)
        log_file_datetime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = path.join(log_dir, f'{job_name}_{log_file_datetime}.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)
        console_handler.setLevel(logging.INFO)
        return logger, console_handler
