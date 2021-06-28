"""
Example code to remove leading and trailing whitespace from Edition titles

This script would be called from the command line like so:
$ python making_a_bot.py --file=~/ol_dump_2020-07.txt.gz --limit=1 --dry-run=True

NOTE: This script assumes the entire OpenLibrary dump is the file argument, but it is almost always faster to pass a grep-filtered dump instead.
You can obtain dumps from https://openlibrary.org/developers/dumps
"""

import copy
import gzip

from olclient.bots import AbstractBotJob


class TrimTitleJob(AbstractBotJob):
    @staticmethod
    def needs_trim(
        edition_title: str,
    ) -> bool:  # it's good practice to make a check method for the pattern you're looking for
        """Returns True if Edition title needs to have whitespace removed. Return false otherwise"""
        return edition_title.strip() != edition_title

    def run(self) -> None:  # overwrite the AbstractBotJob run method
        """Strip leading and trailing whitespace from edition titles"""
        self.dry_run_declaration()

        comment = 'trim whitespace'
        with gzip.open(self.args.file, 'rb') as fin:
            for row in fin:
                # extract info from the dump file and check it
                row, json_data = self.process_row(row)
                if json_data['type']['key'] != '/type/edition':
                    continue  # this can be done faster with a grep filter, but for this example we'll do it here
                if not self.needs_trim(json_data['title']):
                    continue

                # the database may have changed since the dump was created, so call the OpenLibrary API and check again
                olid = json_data['key'].split('/')[-1]
                edition = self.ol.Edition.get(olid)
                if edition.type['key'] != '/type/edition':
                    continue  # skip deleted editions
                if not self.needs_trim(edition.title):
                    continue

                # this edition needs editing, so fix it
                old_title = copy.deepcopy(edition.title)
                edition.title = edition.title.strip()
                # don't forget to log modifications!
                self.logger.info('\t'.join([olid, old_title, edition.title]))
                self.save(lambda: edition.save(comment=comment))


if __name__ == "__main__":
    job = TrimTitleJob()

    try:
        job.run()
    except Exception as e:
        job.logger.exception("")
        raise e
