#!/usr/bin/env python
"""Create the missing Open Library Tags for a managed vocabulary.

Reads an approved ``vocabulary.json`` (the shape used by
open-Book-Genome-Project/tags: a top-level ``tags`` list whose entries carry
``tag``, ``slug``, ``definition`` and an optional ``key``) and creates only the
Tags that don't already exist for the given ``tag_type``. It is idempotent and
**dry-run by default** -- pass ``--write`` to actually create Tags.

Open Library's managed tag_type values are *plural* (``genres``, ``subgenres``,
``audiences``, ``literary_forms``, ``content_formats``). The vocabulary's own
``type`` field and its directory name are *singular* for ``audience`` and
``literary_form`` (internetarchive/openlibrary#13814), so the target tag_type
must be given explicitly with ``--tag-type`` -- it is never derived from the
file. A mismatch between ``--tag-type`` and the file's declared type only warns.

Auth comes from the usual olclient config (``~/.config/ol.ini``); ``--write``
requires valid credentials, a dry-run does not.

Examples:
    # Dry-run: show which content_formats Tags would be created (no writes, no
    # credentials needed):
    python -m olclient.scripts.create_missing_tags \\
        tag_types/content_formats/vocabulary.json --tag-type content_formats

    # Actually create the missing literary_forms Tags, with an edit comment:
    python -m olclient.scripts.create_missing_tags \\
        tag_types/literary_form/vocabulary.json --tag-type literary_forms \\
        --comment "create literary_forms from approved vocabulary" --write

Note the second example on purpose points ``--tag-type literary_forms``
(plural, the target) at the singular ``literary_form/`` directory: the file is
the source of terms, the flag is the type they are created under.
"""

import argparse
import json
import sys

from olclient.openlibrary import OpenLibrary


def load_vocabulary(path):
    """Load an approved vocabulary.json into (declared_type, terms).

    Returns:
        (declared_type, terms) where ``declared_type`` is the file's own
        ``type`` field (may be None / singular) and ``terms`` is a list of
        canonical dicts with keys ``name``, ``slug``, ``description`` and an
        optional ``key`` -- the shape ``Tag.create_missing`` expects.
    """
    with open(path) as f:
        data = json.load(f)
    declared_type = data.get('type')
    terms = []
    for entry in data.get('tags', []):
        term = {
            'name': entry.get('tag', ''),
            'slug': entry.get('slug'),
            'description': entry.get('definition', ''),
        }
        if entry.get('key'):
            term['key'] = entry['key']
        terms.append(term)
    return declared_type, terms


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('vocabulary', help='Path to an approved vocabulary.json')
    parser.add_argument(
        '--tag-type',
        required=True,
        help='The plural managed tag_type to create under '
        '(e.g. content_formats, literary_forms). Given explicitly; not '
        'derived from the file.',
    )
    parser.add_argument(
        '--comment',
        default='create tags from approved vocabulary',
        help='Edit comment recorded on every created Tag.',
    )
    parser.add_argument(
        '-w',
        '--write',
        action='store_true',
        help='Actually create Tags. Omit for a dry-run (the default).',
    )
    parser.add_argument(
        '--baseurl',
        default='https://openlibrary.org',
        help='Which Open Library backend to use.',
    )
    return parser.parse_args(argv)


def run(args, ol=None):
    """Do the work for parsed ``args``. ``ol`` is injectable for testing."""
    declared_type, terms = load_vocabulary(args.vocabulary)
    if declared_type and declared_type != args.tag_type:
        print(
            f"WARNING: vocabulary declares type {declared_type!r} but "
            f"--tag-type is {args.tag_type!r}; using {args.tag_type!r}.",
            file=sys.stderr,
        )

    ol = ol or OpenLibrary(base_url=args.baseurl)
    result = ol.Tag.create_missing(
        args.tag_type, terms, comment=args.comment, write=args.write
    )

    mode = 'WRITE' if args.write else 'DRY-RUN'
    print(f"[{mode}] tag_type={result['tag_type']}")
    print(
        f"  terms: {len(terms)} | already present: "
        f"{len(result['skipped_existing'])} | already keyed: "
        f"{len(result['skipped_has_key'])} | missing: {len(result['to_create'])}"
    )
    if args.write:
        for created in result['created']:
            print(f"  created {created['name']} -> {created['key']}")
        print(f"  created {len(result['created'])} Tag(s).")
    else:
        for name in result['to_create']:
            print(f"  would create: {name}")
        if result['to_create']:
            print("  (dry-run; re-run with --write to create these.)")
        else:
            print("  nothing to create.")
    return result


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    run(args)


if __name__ == '__main__':
    main()
