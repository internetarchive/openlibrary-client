# AGENTS.md

How we work in `openlibrary-client` — conventions for humans and AI agents.
Read this before changing code; read [`docs/`](docs/) for how to *use* the tools.

## What this is

A Python client for the Open Library API, plus the **`ol`** command-line tool
(entry point `ol = olclient.cli:main`). Two layers:

- **`olclient/openlibrary.py`** + `entity_helpers/` — the HTTP client and entity
  models (`Work`, `Edition`, `Author`, `Tag`), auth, and primitives
  (`search_subjects`, `works_by_subject`, `get_many`).
- **`olclient/rule.py`** + **`olclient/cli.py`** — the declarative tagging/subject
  engine and the `ol` CLI built on it.

## The one architectural rule: search vs infogami

This is the seam everything else hangs off:

- **`ol search <plural>` → Solr.** Ranking, facets, discovery. Solr's `type` is
  only `work`/`author`/`subject`, so `ol search editions`/`tags` are **refused**
  and point at the datastore. Solr **lags** edits.
- **`ol <noun>` / writes → infogami datastore** (`query.json`, `get_many`,
  `save_many`). Exact, authoritative, no lag.

**Writes select via the datastore, never a Solr cursor** — Solr lags behind our
own writes, so a cursor over a result set we're mutating skips/dupes. Use Solr to
*find* candidates; use the datastore to *act*.

## Write-safety invariants (never regress these)

Every code path that writes to Open Library keeps all of these:

1. **Dry-run by default.** A write happens only with `--approve`. `--show-payload`
   prints the exact `save_many` request and writes nothing.
2. **Identity guard.** Before writing, `assert_identity(ol, expected_account)`
   aborts unless the session really is the expected account (default
   `openlibrarytagsbot`). Never write as whoever happens to be in `ol.ini`.
3. **Lost-update guard.** Re-fetch each work's live revision immediately before
   saving (batched via `get_many`) and skip any work edited/vanished since
   planning — never clobber a concurrent edit.
4. **Reversible audit.** With `--audit <file>`, every written work logs its
   base revision + per-field before/after, after the batch is accepted (never a
   phantom row on a failed POST).
5. **Idempotent + resumable.** Re-running converges (already-satisfied works are
   no-ops); long runs record progress and skip done work on resume.

## Batching & resilience (the WAF shapes this)

Open Library's ModSecurity WAF caps a request body at `SecArgumentsLimit` (6000
parsed args) and denies with **HTTP 460**. So:

- **Reads are batched** via `get_many` (chunks of 100) — never a GET per work.
  A serial fetch-per-work both crawls and triggers connection resets.
- **Writes are packed** by `pack_batches` under a hard arg budget, and
  `_save_with_split` splits a batch on any save error down to the single
  offending work, which it **skips** (reported) rather than aborting the batch or
  the whole subject. One poison work can't sink a 39k-work run.

## The rule engine model

A `Rule` is a **selector** (subjects whose works to touch) + a **change** (tags to
add, subject strings to add, subjects to remove). `plan_rule` computes a
read-only plan; `apply_rule` writes it (honoring the invariants above). The CLI
verbs are thin wrappers:

- `ol subject --merge A B --into C` — fold spelling variants into one.
- `ol subject --select … --add-tags …` — tag works by subject (datastore union).
- `ol tag add TAG --subjects a,b,c` — tag works matching ALL subjects (Solr AND).

See [`docs/subject-tagging.md`](docs/subject-tagging.md) for worked examples.

## Code style

- **Docstrings on every public module, class, and function.** Non-trivial public
  functions carry a `Usage:` doctest; mark it `# doctest: +SKIP` when it needs
  network or credentials. This is the house style — match it.
- Keep lines reasonable (~100 cols). `ruff` runs in pre-commit
  (`extend-select = C4, C9, PLC, PLE, W`, mccabe max-complexity 33). Note:
  `line-length` in `pyproject.toml` is currently `1501` (a typo for `150`); don't
  rely on it to catch long lines.
- Prefer small, named helpers over clever one-liners; a reader should grok a
  function without holding the whole module in their head. Don't add an
  abstraction until there's real, demonstrated duplication.

## Testing

- `make test-py` (or `python -m pytest -q`). **No network in unit tests** — drive
  the engine and CLI through the shared fakes in `tests/conftest.py`
  (`FakeOL`, `FakeResponse`, `FakeTag`, `patch_authed_ol`, `make_*_args`). Add new
  fakes there, not per-file.
- Every change keeps the suite green and lands as its own commit. Integration
  tests under `tests/integration/` need a running OL (`OL_TEST_URL`) and are
  skipped otherwise.

## Operational notes

- `openlibrary-bot` **cannot push to upstream** (forks only). Pushes to
  `internetarchive/openlibrary-client` go through a maintainer (`gh` =
  `mekarpeles`).
- Production writes (`--approve`) are deliberate, bounded, and (for bulk
  campaigns) run as resumable background jobs with an audit log.
