# Subject tagging & cleanup

How we tag works and clean up duplicate subjects on Open Library with `ol`, with
real examples. For the CLI reference see [`cli.md`](cli.md); for conventions see
[`../AGENTS.md`](../AGENTS.md).

Two things to internalise first:

- **Select via the datastore, discover via Solr.** Solr lags edits, so a Solr
  cursor over works you're actively mutating will skip or double-count. Use Solr
  (`ol search`, `/search/subjects.json`) to *find* candidates; use the datastore
  (`--select` / `works_by_subject`) to *act* on them.
- **Nothing writes without `--approve`.** Build every command as a dry run first,
  read the preview, then add `--approve`.

## Pattern 1 — merge spelling variants (and tag) in one pass

Many works carry the same subject under many spellings. One command selects the
union, removes the messy spellings, adds a canonical, and tags — **one
`save_many` write per work**.

Real example (steampunk):

```sh
ol subject --merge \
  "Steampunk fiction" "Steampunk Science Fiction" "steampunk fiction" \
  "Fiction, science fiction, steampunk" \
  "FICTION -- Science Fiction -- Steampunk" \
  "FICTION / Science Fiction / Steampunk" \
  --into "Steampunk" \
  --add-tags subgenre:steampunk literary_form:fiction "genre:Sci-Fi" \
  --audit steampunk.audit.jsonl --approve
```

What happens per matched work: add the three Tags (routed by `tag_type` to
`subgenres`/`literary_forms`/`genres`), remove the six listed subjects, add
`"Steampunk"`. It's idempotent — a work that already has the canonical and tags
is a no-op, so re-running converges. Drop `--approve` to see the plan and
per-work diffs first.

Note the resolver refuses a tag it can't find: `genre:Science Fiction` errors
because the genre vocabulary calls it **Sci-Fi** — a guard against mis-tagging,
not a bug.

## Pattern 2 — tag a large set of works by subject (bulk campaign)

Example: tag every work whose subject mentions "Nonfiction"/"Non-fiction" as
`literary_form:Nonfiction`.

**Find the candidates** (Solr). The untagged set:

```
subject:(Nonfiction OR "non fiction") AND -literary_form_name:Nonfiction
```

and the distinct subject strings to iterate come from
`/search/subjects.json?q=nonfiction` (+ `q=non-fiction`), filtered to the ones
that really contain the substring. Save them one-per-line.

**Act** (datastore), as a resumable background job:

```sh
ol subject --select-file nonfiction-subjects.txt \
  --add-tags literary_form:nonfiction \
  --audit nonfiction.audit.jsonl \
  --progress-file nonfiction.progress \
  --approve
```

- Iterates one subject at a time via `works_by_subject` (no Solr lag).
- `--progress-file` records each completed subject; interrupt and re-run to
  **resume** (done subjects are skipped, and already-tagged works are no-ops).
- A single work the server rejects (e.g. a persistent `403`/`500` on one record)
  is **skipped and reported**, not fatal — the rest of the subject still tags.

Start with the long tail (the many small subjects) and defer the few giant ones
to their own run; `ol search subjects --query nonfiction --max-works 10` and
`/search/subjects.json` help you bucket by size.

## Pattern 3 — tag works matching ALL of several subjects

When a classification only holds where several subjects are true together, use
the AND selector:

```sh
ol tag add OL167T --subjects graphic_design,paintings,art_german
```

Tags every work carrying **all** three subject slugs (and not already tagged).
This is the one selector that uses Solr search, because `query.json` can't AND
two values of the same field; correctness still holds because each work is
re-checked before writing.

## Safety

Every write path keeps these — see [`../AGENTS.md`](../AGENTS.md#write-safety-invariants-never-regress-these):

- **Dry-run by default / `--approve` to write / `--show-payload`** to inspect the
  exact request.
- **Identity guard** — refuses to write unless the session is the expected
  account (`--as`, default `openlibrarytagsbot`).
- **Lost-update guard** — re-reads each work's revision right before saving and
  skips anything edited since planning.
- **Reversible audit** (`--audit`) — base revision + per-field before/after for
  every written work.
- **Resumable progress** (`--progress-file`) + idempotency for long campaigns.

### After a run: Solr lag

Work edits are immediate in the datastore but **Solr catches up on a delay**, and
the subject *search* index (`/search/subjects.json`, `type:subject` docs) is
rebuilt by a separate batch job — so a subject can show 0 works on its page while
still appearing in subject search for a while. That's expected; verify writes
against the datastore (`/works/<id>.json`), not Solr, right after a run.
