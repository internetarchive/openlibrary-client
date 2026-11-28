# The `ol` command line

`ol` is a gh-style, noun/verb CLI for Open Library (entry point
`olclient.cli:main`). The guiding seam:

- **`ol search <plural>`** → Solr (ranking, facets, discovery).
- **`ol <noun> …`** → the infogami datastore (exact records and writes).

Run `ol <command> --help` for the full flag list. Everything that writes is a
**dry run until you pass `--approve`**.

## `ol configure`

Stores IA/OL credentials (S3 keys) in `~/.config/ol.ini` so you don't pass
credentials per request.

```sh
ol configure --email you@archive.org
```

## `ol search` — Solr

```sh
ol search works    --query "dune" --limit 20
ol search authors  --query asimov --limit 10
ol search subjects --query fantasy --max-works 10 --limit 100
```

- Entity must be `works`, `authors`, or `subjects`. `editions`/`tags` are
  **refused** (they're datastore objects, not Solr types).
- `subjects` supports `--max-works N` (keep subjects appearing in ≤ N works) for
  finding cleanup candidates.
- `--json` emits JSON; reads `$OL_SOLR_BASE_URL` (or `--solr`).
- **A bare `ol search subjects` is refused** — give at least one of `--query`,
  `--max-works`, or `--limit`, since enumerating the whole subject vocabulary is
  unbounded.

## `ol subject` — merge, clean, and tag subjects (writes)

Operates on works via the datastore. Three modes:

### `--merge` — fold spelling variants into one

```sh
ol subject --merge "World War, 1939-1945" "World war, 1939-1945" \
  --into "World War, 1939-1945"
```

Selects works carrying **any** of the listed subjects (OR), removes them, and
adds the survivor. `--into/--keep/--winner/--choose` names the survivor; without
it, the highest-work-count variant wins (note: that count comes from
`/search/subjects.json`, which is normalised/lagging — prefer an explicit
`--into`).

### `--select` — tag works carrying a subject (no removal)

```sh
ol subject --select "Creative nonfiction" "Non-English Nonfiction" \
  --add-tags literary_form:nonfiction
# or, for a long list, one subject per line:
ol subject --select-file nonfiction-subjects.txt \
  --add-tags literary_form:nonfiction \
  --audit run.audit.jsonl --progress-file run.progress --approve
```

Iterates **one subject at a time** via the datastore (no Solr cursor), keeps the
subject, and applies `--add-tags`/`--add`. `--progress-file` makes it resumable;
`--select` defaults to **all** works per subject.

### `--remove … --add …` — drop/add subject strings

```sh
ol subject --remove "A" "B" --add "C"
```

### `--add-tags`

`<tag_type>:<name>` (resolved case-insensitively to a Tag) or a `/tags/OL…T`
key — e.g. `subgenre:steampunk literary_form:fiction "genre:Sci-Fi"`. Multiple
tags in the same field are all added.

## `ol tag add` — tag works matching ALL of a set of subjects (writes)

```sh
ol tag add OL167T --subjects graphic_design,paintings,art_german
```

Tags every work carrying **all** of the given subject slugs (AND — selected via
`/search.json`, since `query.json` can't AND two values of one field).
`--rm-subjects` removes subjects by slug; `--limit` caps the number of works
(default 100).

## Global write flags (`subject`, `tag add`)

| Flag | Effect |
|---|---|
| `--approve` | Apply the write. Without it, a dry run / confirmation prompt. |
| `--dry-run` | (`subject`) preview only; write nothing. |
| `--show-payload` | Print the exact `/api/save_many` request; write nothing. |
| `--audit <file>` | Append a reversible JSONL record per written work. |
| `--as <account>` | Refuse to write unless the session is this account (default `openlibrarytagsbot`). |
| `--batch-size N` | Works per `save_many` POST (default 100; auto-split if the WAF rejects). |
| `--comment` | The edit comment. |

See [`subject-tagging.md`](subject-tagging.md) for end-to-end examples and the
safety model.
