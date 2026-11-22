#!/usr/bin/env python

"""
    cli.py
    ~~~~~~

    The ``ol`` command line (v2) — a gh-style, noun/verb CLI for Open Library.

        ol search subjects --query fantasy --max-works 10 --limit 100
        ol search works    --query dune --limit 20
        ol subject --merge "Fiction - Fantasy" "Fiction, fantasy"
        ol subject --remove "A" "B" --add "C"
        ol configure --email you@archive.org

    Design seam — **search vs infogami**:
      * ``ol search <plural>``  -> Solr (ranking, facets; works/authors/subjects).
      * ``ol <noun> …``         -> infogami datastore (exact records / writes).
    Solr owns work/author/subject; editions and tags are datastore objects, so
    ``ol search`` refuses them and points at the datastore.

    :copyright: (c) 2016-2026 by Internet Archive.
    :license: see LICENSE for more details.
"""

import argparse
import getpass
import json
import sys
from urllib.parse import urlencode

from olclient import __title__, __version__, OpenLibrary
from olclient.config import Config, Credentials
from olclient.rule import (
    Rule, apply_rule, build_save_docs, format_plan, logged_in_user,
    plan_rule, save_many_request,
)
from olclient.search import (
    ENTITY_CHOICES, INFOGAMI_TYPES, search_docs, search_subjects,
)
from olclient.solr import http_get_json, solr_base


def _authed_ol(baseurl=None):
    """An authenticated OpenLibrary client (for datastore reads/writes)."""
    try:
        return OpenLibrary(base_url=baseurl) if baseurl else OpenLibrary()
    except ValueError as e:
        if str(e) == "No cookie set":
            raise SystemExit(
                "not configured — run:  ol configure --email <you@archive.org>"
            )
        raise


# ---------------------------------------------------------------------------
# ol search <type>  — Solr
# ---------------------------------------------------------------------------

def cmd_search(args):
    if args.type in INFOGAMI_TYPES:
        raise SystemExit(f"ol search {args.type}: {INFOGAMI_TYPES[args.type]}")
    base = solr_base(args.solr)
    if args.type == "subjects":
        rows = search_subjects(http_get_json, base, query=args.query,
                               max_works=args.max_works, limit=args.limit)
        if args.json:
            json.dump([{"name": n, "work_count": c} for n, c in rows],
                      sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            for name, count in rows:
                print(f"{count}\t{name}")
        n = len(rows)
    else:
        if args.max_works is not None:
            print("note: --max-works only applies to 'subjects'; ignoring", file=sys.stderr)
        docs = search_docs(http_get_json, base, args.type, query=args.query, limit=args.limit)
        if args.json:
            json.dump(docs, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            for d in docs:
                label = d.get("title") or d.get("name") or ""
                if d.get("author_name"):
                    label += "  —  " + ", ".join(d["author_name"])
                print(f"{d.get('key', '')}\t{label}")
        n = len(docs)
    print(f"# {n:,} {args.type}", file=sys.stderr)


# ---------------------------------------------------------------------------
# ol subject  — infogami write: merge variants, or remove/add (dedup)
# ---------------------------------------------------------------------------

def pick_winner(count_fn, variants, into=None):
    """Survivor of a merge: an explicit --into, else the highest-work_count variant."""
    if into:
        return into
    return max(variants, key=lambda v: count_fn(v) or 0)


def _resolve_add_tags(ol, refs):
    """Resolve each ``<tag_type>:<name>`` (or ``/tags/OL..T``) ref to a Tag key.

    The name is matched case-insensitively against existing Tags of that
    tag_type (via ``Tag.find``). Zero matches or more than one is a hard error
    rather than a guess, so a write never attaches the wrong Tag.
    """
    keys = []
    for raw in refs:
        ref = raw.strip()
        if ref.startswith("/tags/"):
            keys.append(ref)
            continue
        if ":" not in ref:
            raise SystemExit(f"--add-tags {raw!r} must be <tag_type>:<name> or /tags/OL..T")
        tag_type, value = (p.strip() for p in ref.split(":", 1))
        matches = ol.Tag.find(tag_type, name=value)
        if not matches:
            raise SystemExit(f"--add-tags: no {tag_type} Tag named {value!r}")
        if len(matches) > 1:
            olids = ", ".join(f"/tags/{m.olid}" for m in matches)
            raise SystemExit(f"--add-tags {raw!r} is ambiguous ({len(matches)}): {olids}")
        keys.append(f"/tags/{matches[0].olid}")
    return keys


def _execute(ol, plan, *, comment, show_payload, dry_run, yes, batch_size,
             audit, as_account):
    """Preview, then (unless previewing/dry-running) write a plan via the engine.

    Shared by ``ol subject`` and ``ol tag add``: inspect the exact request
    (``show_payload``), stop at a dry run, otherwise confirm (unless ``yes``)
    and apply with the identity guard and reversible audit.
    """
    if show_payload:
        docs = build_save_docs(ol, plan, comment=comment)
        req = save_many_request(ol, docs, comment=comment)
        print(f"POST {req['url']}")
        for k, v in req["headers"].items():
            print(f"  {k}: {v}")
        print(f"  (would write as: {logged_in_user(ol)})")
        print(f"\nBODY ({len(docs)} work doc(s)):")
        print(json.dumps(req["body"], indent=2, ensure_ascii=False))
        return

    if dry_run:
        s = apply_rule(ol, plan, comment=comment, dry_run=True)
        print(f"DRY RUN: would write {s['would_write']:,} works in {s['batches']} batch(es). "
              f"Use --yes to apply.")
        return

    n = len(plan.to_write)
    if n == 0:
        print("Nothing to write — every examined work already satisfies this.")
        return
    if not yes:
        if input(f"Write {n} work(s) as {logged_in_user(ol)}? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return
    s = apply_rule(ol, plan, comment=comment, batch_size=batch_size,
                   dry_run=False, audit=audit, expected_account=as_account)
    print(f"WROTE {s['written']:,} of {s['planned']:,} planned works.")
    if audit:
        print(f"Reversible audit log: {audit}")


def cmd_subject(args):
    ol = _authed_ol(args.baseurl)
    st = args.type

    def count_of(name):
        hits = list(ol.search_subjects(name, limit=25, subject_type=st))
        for hit in hits:  # exact case first (case-only variants are distinct)
            if hit.get("name") == name:
                return hit.get("work_count") or 0
        for hit in hits:
            if hit.get("name", "").lower() == name.lower():
                return hit.get("work_count") or 0
        return 0

    if args.merge:
        variants = list(dict.fromkeys(args.merge))
        if len(variants) < 2 and not args.into:
            raise SystemExit("ol subject --merge needs >=2 subjects (or 1 plus --into)")
        winner = pick_winner(count_of, variants, args.into)
        # Selector is exactly the listed subjects (the union to touch). The
        # winner is the survivor flagged keep; when it is a *new* canonical
        # (not among the variants) it is added via add_subjects only, so we
        # never pull in every existing work already carrying it.
        subjects = [(v, 1 if v == winner else 0) for v in variants]
        add_subjects = [winner]
        print(f"merge winner: {winner!r}\n")
    else:
        if not args.remove:
            raise SystemExit("ol subject: use --merge, or --remove ... [--add ...]")
        subjects = [(s, 0) for s in args.remove]
        add_subjects = list(args.add or [])

    add_tags = _resolve_add_tags(ol, args.add_tags) if args.add_tags else []
    rule = Rule(add_tags=add_tags, subjects=subjects, add_subjects=add_subjects, subject_type=st)
    plan = plan_rule(ol, rule, limit=args.limit)
    print(format_plan(plan, args.limit))
    print()
    _execute(ol, plan, comment=args.comment, show_payload=args.show_payload,
             dry_run=args.dry_run, yes=args.yes, batch_size=args.batch_size,
             audit=args.audit, as_account=args.as_account)


# ---------------------------------------------------------------------------
# ol tag add  — tag every work carrying ALL of a set of subjects (issue #458)
# ---------------------------------------------------------------------------

def _works_matching_all_subjects(ol, slugs, exclude_tag_key=None, tag_type=None,
                                 tag_olid=None, limit=100):
    """Work keys carrying ALL ``slugs`` (AND), via the public /search.json.

    ``/query.json`` can't AND two values of the same field, so this uses Solr
    search: ``subject_key:a AND subject_key:b [AND -<tag_type>_key:OLID]``.
    The optional exclusion skips works already carrying the Tag; correctness
    does not depend on it (the plan re-checks each work and no-ops any that
    already have the Tag), it just avoids fetching them.
    """
    clauses = [f"subject_key:{slug}" for slug in slugs]
    if tag_type and tag_olid:
        clauses.append(f"-{tag_type}_key:{tag_olid}")
    params = {"q": " AND ".join(clauses), "fields": "key", "limit": limit}
    resp = ol.get_ol_response(f"/search.json?{urlencode(params)}")
    return [d["key"] for d in resp.json().get("docs", []) if d.get("key")]


def cmd_tag_add(args):
    ol = _authed_ol(args.baseurl)

    olid = args.tag_olid.rstrip("/").split("/")[-1]
    tag = ol.Tag.get(olid)
    if tag is None:
        raise SystemExit(f"Tag /tags/{olid} does not exist")
    tag_key = f"/tags/{olid}"
    tag_type = getattr(tag, "tag_type", None)

    slugs = [s.strip() for s in args.subjects.split(",") if s.strip()]
    if not slugs:
        raise SystemExit("ol tag add: --subjects needs at least one slug")
    rm_slugs = [s.strip() for s in (args.rm_subjects or "").split(",") if s.strip()]

    work_keys = _works_matching_all_subjects(
        ol, slugs, tag_type=tag_type, tag_olid=olid, limit=args.limit)
    print(f"tag: {getattr(tag, 'name', None) or tag_key} ({tag_type})  {tag_key}")
    print(f"select works with ALL subjects: {', '.join(slugs)}")
    if rm_slugs:
        print(f"  and remove subjects by slug: {', '.join(rm_slugs)}")
    print(f"  {len(work_keys):,} candidate work(s) from search\n")

    rule = Rule(add_tags=[tag_key], subjects=[], remove_subject_slugs=rm_slugs)
    plan = plan_rule(ol, rule, limit=args.limit, work_keys=work_keys)
    print(format_plan(plan, args.limit))
    print()
    _execute(ol, plan, comment=args.comment, show_payload=args.show_payload,
             dry_run=not args.yes, yes=args.yes, batch_size=args.batch_size,
             audit=args.audit, as_account=args.as_account)


# ---------------------------------------------------------------------------
# ol configure
# ---------------------------------------------------------------------------

def cmd_configure(args):
    import internetarchive as ia

    email = args.email or input("Archive.org Email: ")
    if not email:
        raise SystemExit("--email required for configuration")
    password = getpass.getpass("Password: ")
    ia.configure(email, password, host="archive.org")
    config_tool = Config()
    config = config_tool._get_config()
    config["s3"] = ia.config.get_config()["s3"]
    try:
        OpenLibrary(credentials=Credentials(**config["s3"]), base_url=args.baseurl)
    except Exception:
        raise SystemExit("Incorrect credentials, not updating config.")
    config_tool.update(config)
    print("Successfully configured")


# ---------------------------------------------------------------------------
# parser / entry point
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="ol", description=__title__)
    p.add_argument("-v", action="version", version=f"{__title__} v{__version__}")
    p.add_argument("--baseurl", default=None, help="Which OL backend to use")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="Search Solr (works, authors, subjects)")
    sp.add_argument("type", choices=ENTITY_CHOICES, help="entity type to search")
    sp.add_argument("--query", "-q", default=None,
                    help="search term (subjects: substring match on the name)")
    sp.add_argument("--limit", type=int, default=None, help="cap the number of results")
    sp.add_argument("--max-works", type=int, default=None,
                    help="subjects only: keep subjects appearing in <= N works")
    sp.add_argument("--solr", default=None, help="Solr base URL (default: $OL_SOLR_BASE_URL)")
    sp.add_argument("--json", action="store_true", help="emit JSON")

    mp = sub.add_parser("subject", help="Merge/clean subjects on works (writes via infogami)")
    mp.add_argument("--merge", nargs="+", metavar="SUBJECT",
                    help="merge these subject variants into one winner")
    mp.add_argument("--into", "--keep", "--winner", "--choose", dest="into",
                    default=None, metavar="SUBJECT",
                    help="the survivor for --merge (default: highest work_count)")
    mp.add_argument("--remove", nargs="+", metavar="SUBJECT",
                    help="remove these subjects from matching works")
    mp.add_argument("--add", nargs="+", metavar="SUBJECT",
                    help="add these subject strings to matching works")
    mp.add_argument("--add-tags", nargs="+", dest="add_tags", metavar="TAG",
                    help="also add these Tags to every matching work, as "
                         "<tag_type>:<name> (e.g. genre:'Science Fiction') or /tags/OL..T")
    mp.add_argument("--type", dest="type", default="subject",
                    choices=["subject", "person", "place", "time"])
    mp.add_argument("--limit", type=int, default=50, help="max works to examine/write")
    mp.add_argument("--batch-size", type=int, default=250)
    mp.add_argument("--comment", default="merge/clean subjects")
    mp.add_argument("--audit", default=None, help="reversible audit JSONL path")
    mp.add_argument("--dry-run", action="store_true", help="preview only; write nothing")
    mp.add_argument("--show-payload", action="store_true",
                    help="print the exact /api/save_many request; write nothing")
    mp.add_argument("--as", dest="as_account", default="openlibrarytagsbot",
                    help="refuse to write unless the session is this account")
    mp.add_argument("--yes", action="store_true", help="skip the confirmation prompt")

    tp = sub.add_parser("tag", help="Tag works (writes via infogami)")
    tsub = tp.add_subparsers(dest="tag_command", required=True)
    ta = tsub.add_parser("add", help="Tag every work carrying ALL of a set of subjects")
    ta.add_argument("tag_olid", metavar="TAG_OLID", help="the Tag to add, e.g. OL167T")
    ta.add_argument("--subjects", required=True, metavar="SLUG[,SLUG...]",
                    help="subject slugs (as in /subjects/<slug>); a work must have ALL")
    ta.add_argument("--rm-subjects", dest="rm_subjects", default=None,
                    metavar="SLUG[,SLUG...]", help="subject slugs to remove from each tagged work")
    ta.add_argument("--limit", type=int, default=100, help="max works to change (default 100)")
    ta.add_argument("--batch-size", type=int, default=250)
    ta.add_argument("--comment", default="tag works by subject")
    ta.add_argument("--audit", default=None, help="reversible audit JSONL path")
    ta.add_argument("--show-payload", action="store_true",
                    help="print the exact /api/save_many request; write nothing")
    ta.add_argument("--as", dest="as_account", default="openlibrarytagsbot",
                    help="refuse to write unless the session is this account")
    ta.add_argument("--yes", action="store_true",
                    help="save the changes (without it, this is a dry run)")

    cp = sub.add_parser("configure", help="Store IA/OL credentials")
    cp.add_argument("--email", default=None, help="Archive.org email")

    return p


def cmd_tag(args):
    {"add": cmd_tag_add}[args.tag_command](args)


def main(argv=None):
    args = build_parser().parse_args(argv)
    {"search": cmd_search, "subject": cmd_subject, "tag": cmd_tag,
     "configure": cmd_configure}[args.command](args)


if __name__ == "__main__":
    main()
