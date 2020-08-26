"""
Example code to remove leading and trailing whitespace from Edition titles

This script would be called from the command line like so:
$ python making_a_bot.py --file=~/ol_dump_2020-07.txt.gz --limit=1 --dry-run=True

NOTE: This script assumes the entire OpenLibrary dump is the file argument, but it is almost always faster to pass a grep-filtered dump instead.
You can obtain dumps from https://openlibrary.org/developers/dumps
"""

import copy
import gzip
import json

from olclient.bots import BaseBot


class TrimBot(BaseBot):
    @staticmethod
    def needs_trim(edition_title: str) -> bool:  # it's good practice to make a check method for the pattern you're looking for
        """Returns True if Edition title needs to have whitespace removed. Return false otherwise"""
        return edition_title.strip() != edition_title

    def run(self) -> None:  # overwrite the BaseBot run method
        """Strip leading and trailing whitespace from edition titles"""
        if self.dry_run:
            self.logger.info('dry-run set to TRUE. Script will run, but no external modifications will be made.')

        header = {'type': 0,
                  'key': 1,
                  'revision': 2,
                  'last_modified': 3,
                  'JSON': 4}
        comment = 'trim whitespace'
        with gzip.open(self.args['file'], 'rb') as fin:
            for row in fin:
                # parse the dump file and check it
                row = row.decode().split('\t')
                json_data = json.loads(row[header['JSON']])
                if json_data['type']['key'] != '/type/edition': continue  # this can be done faster with a grep filter, but for this example we'll do it here
                if not self.needs_trim(json_data['title']): continue

                # the database may have changed since the dump was created, so call the OpenLibrary API and check again
                olid = json_data['key'].split('/')[-1]
                edition = self.ol.Edition.get(olid)
                if edition.type['key'] != '/type/edition': continue  # skip deleted editions
                if not self.needs_trim(edition.title): continue

                # this edition needs editing, so fix it
                old_title = copy.deepcopy(edition.title)
                edition.title = edition.title.strip()
                self.logger.info('\t'.join([olid, old_title, edition.title]))  # don't forget to log modifications!
                self.save(lambda: edition.save(comment=comment))


if '__name__' == __name__:
    bot = TrimBot()

    try:
        bot.run()
    except Exception as e:
        bot.logger.exception("")
        raise e
