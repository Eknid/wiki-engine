# Wiki Engine

Reusable tools and Claude Code skills for maintaining a local Markdown wiki. This repository contains **only the engine**: no domain pages, raw sources, deliverables, search indexes, or content from the wiki it was extracted from.

## Create a wiki

Requirements: Python 3.10+ and Git. Claude Code is needed for the assisted ingest, query, save, and lint skills. Obsidian and Ollama are optional.

```bash
python3 wiki_engine.py init ../my-project-wiki --domain "Project A" --scope "Architecture and decisions for Project A"
cd ../my-project-wiki
python3 scripts/wiki-check.py --ci
python3 scripts/wiki-search.py index
python3 scripts/wiki-search.py query "architecture"
```

Open the generated folder as a Git repository and work from its root. `init` creates one empty domain, a hub, a registry, templates, scripts, skills, and CI. It does not invent project knowledge. Add a source through `/wiki-ingest` or put existing Markdown pages into the domain and update their frontmatter and catalog.

## Add the engine to an existing wiki

```bash
python3 wiki_engine.py install /path/to/your-wiki
```

The installer copies only engine-owned files (`scripts/`, `.claude/skills/wiki-*`, the worker agent, `WIKI.md`, and CI). It leaves content and `.vault-meta/domains.json` alone. On later installs it updates files that still match the previous engine version. If you edited an engine file locally, it reports a conflict and keeps your edit. Existing wikis need a domain registry in `.vault-meta/domains.json`; see the sample below. Installing `.claude/settings.json` enables a session context hook and a reminder to refresh the hot cache. It does not auto-commit.

```json
{
  "domains": [
    {"folder": "Project A", "wiki": "project-a", "label": "Project A", "prefix": "Project A — ", "scope": "Architecture and decisions"}
  ]
}
```

The engine expects `wiki/{index,hot,log}.md` at the root, plus `<Domain>/wiki/{index,hot,log}.md` for each registered domain. Put knowledge pages under `<Domain>/wiki/`, raw sources under `<Domain>/.raw/`, and shareable documents under `<Domain>/deliverables/`. Use unique filenames for content pages throughout the vault.

## Maintain the wiki

- `/wiki-ingest`: read a source, create linked pages, update catalogs and recent context.
- `/wiki-query`: answer by routing through indexes, scoped search, and links.
- `/wiki-save`: keep a useful answer or decision.
- `/wiki-lint`: run structural checks and review quality.
- `/wiki-new-domain`: add and register another sub-wiki.
- `scripts/wiki-check.py --ci`: check page metadata, names, and links in CI.
- `scripts/wiki-graph.py neighbors "Page Name"`: inspect related pages.
- `scripts/wiki-search.py index` and `query`: local keyword search. Optional Ollama embeddings add hybrid search.

The Python tools use only the standard library. They run against their installed wiki root. Set `WIKI_ROOT=/path/to/wiki` to point them at another vault.

## What is distributed

`engine/` holds the installable files. `wiki_engine.py` creates or updates a vault. The third-party notice in `engine/.claude/NOTICE.md` covers the adapted claude-obsidian skills and search design. See [LICENSE](LICENSE).
