# openlibrary-client docs

Guides for using the client library and the **`ol`** command-line tool, for both
humans and AI agents. For *how we write the code*, see [`../AGENTS.md`](../AGENTS.md).

| Guide | What it covers |
|---|---|
| [`cli.md`](cli.md) | The `ol` command line — `search`, `subject`, `tag add`, `configure`, and the global write flags. |
| [`subject-tagging.md`](subject-tagging.md) | Worked workflows: tagging works by subject, merging duplicate subjects, and the safety model — with real examples (biography, nonfiction, steampunk). |

## Quick orientation

- **Install & configure:** see the top-level [`../README.md`](../README.md)
  (`ol configure` stores your IA/OL credentials).
- **One rule to hold in your head:** `ol search …` hits **Solr** (discovery,
  lags edits); everything else (reads for writing, and all writes) goes through
  the **infogami datastore** (exact, no lag). See [`../AGENTS.md`](../AGENTS.md).
- **Nothing writes without `--approve`.** Every command is a dry run by default
  and prints exactly what it would change.

## For agents

Before a bulk write, read [`subject-tagging.md`](subject-tagging.md#safety) — the
dry-run/`--approve`, identity-guard, reversible-audit, and resumable-progress
model is not optional. Select the works to change via the datastore
(`--select`/`works_by_subject`), not a Solr cursor, because Solr lags your own
writes.
