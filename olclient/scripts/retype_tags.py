#!/usr/bin/env python
"""Rename the tag_type of existing Open Library Tags (singular -> plural).

Open Library has a handful of Tags carrying the older *singular* tag_type
values and being migrated to their plural form
(internetarchive/openlibrary#13814): ``audience`` -> ``audiences``,
``literary_form`` -> ``literary_forms``, ``genre`` -> ``genres``. For these,
"create missing" is a no-op (the Tags already exist); what's needed is to
re-type the existing Tags, which this does.

It is **dry-run by default**; pass ``--write`` to re-save. ``--to-type``
defaults to the known plural for a recognised singular ``--from-type``, but can
be given explicitly. Editing a Tag does NOT reindex the works that reference it,
so this is a small change -- but it is still a production write that needs a
maintainer's sign-off. Auth comes from the usual olclient config
(``~/.config/ol.ini``); ``--write`` requires valid credentials.

Examples:
    # Dry-run: list the Tags that would be retyped literary_form -> literary_forms
    python -m olclient.scripts.retype_tags --from-type literary_form

    # Actually retype the singular 'genre' Tag(s) to 'genres'
    python -m olclient.scripts.retype_tags --from-type genre --to-type genres \\
        --comment "retype genre -> genres (#13814)" --write
"""

import argparse
import sys

from olclient.openlibrary import OpenLibrary, SINGULAR_TO_PLURAL_TAG_TYPE


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--from-type',
        required=True,
        help='The current tag_type to rename (e.g. literary_form).',
    )
    parser.add_argument(
        '--to-type',
        default=None,
        help='The new tag_type. Defaults to the known plural for a recognised '
        'singular --from-type.',
    )
    parser.add_argument(
        '--comment',
        default='rename tag_type',
        help='Edit comment recorded on every retyped Tag.',
    )
    parser.add_argument(
        '-w',
        '--write',
        action='store_true',
        help='Actually re-save Tags. Omit for a dry-run (the default).',
    )
    parser.add_argument(
        '--baseurl',
        default='https://openlibrary.org',
        help='Which Open Library backend to use.',
    )
    return parser.parse_args(argv)


def resolve_to_type(from_type, to_type):
    """Returns the explicit to_type, or the known plural for from_type."""
    if to_type:
        return to_type
    return SINGULAR_TO_PLURAL_TAG_TYPE.get(from_type)


def run(args, ol=None):
    """Do the work for parsed ``args``. ``ol`` is injectable for testing."""
    to_type = resolve_to_type(args.from_type, args.to_type)
    if not to_type:
        print(
            f"ERROR: no --to-type given and {args.from_type!r} has no known "
            f"plural; pass --to-type explicitly.",
            file=sys.stderr,
        )
        return None

    ol = ol or OpenLibrary(base_url=args.baseurl)
    result = ol.Tag.retype(
        args.from_type, to_type, comment=args.comment, write=args.write
    )

    mode = 'WRITE' if args.write else 'DRY-RUN'
    print(f"[{mode}] {result['from_type']} -> {result['to_type']}")
    print(f"  {len(result['to_retype'])} Tag(s) of type {result['from_type']!r}")
    if args.write:
        for t in result['retyped']:
            print(f"  retyped {t['name']} ({t['key']})")
        print(f"  retyped {len(result['retyped'])} Tag(s).")
    else:
        for t in result['to_retype']:
            print(f"  would retype: {t['name']} (/tags/{t['olid']})")
        if result['to_retype']:
            print("  (dry-run; re-run with --write to retype these.)")
        else:
            print("  nothing to retype.")
    return result


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    run(args)


if __name__ == '__main__':
    main()
