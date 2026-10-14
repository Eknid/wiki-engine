# Wiki page format

This is the shared format for hub, shared, and domain pages. Domain names and scopes live in `.vault-meta/domains.json` and `CLAUDE.md`.

## Layout

- `<Domain>/.raw/`: immutable source captures.
- `<Domain>/wiki/`: linked knowledge pages and catalogs.
- `<Domain>/_templates/`: starter structures for pages.
- `<Domain>/deliverables/`: documents written for sharing; no wiki frontmatter required.
- `wiki/`: hub index, recent context, log, shared pages, and cross-domain questions.

## Frontmatter

Every page under `wiki/` or `<Domain>/wiki/` needs `type:` and `wiki:`. Use `hub` for hub pages, `shared` for `wiki/shared/`, and the registered domain value for domain pages.

```yaml
---
type: concept
title: "Example Concept"
wiki: project-a
status: seed
created: 2026-01-01
updated: 2026-01-01
tags:
  - type/concept
related: []
sources: []
---
```

Keep YAML flat. Use one idea per page and unique page filenames across the vault. Link by `[[Page Name]]`, using a path for repeated system page names. Cite source pages or raw captures. Mark gaps and contradictions with Obsidian callouts.

## Navigation and maintenance

Each wiki has `index.md` for its catalog, `hot.md` for a recent context cache under 500 words, and `log.md` with newest entries first. Add a catalog line and log entry when creating a page. Shared pages list consuming domains in `used_in:` and have one `## In <Domain Label>` section for each.

Run `python3 scripts/wiki-check.py --ci` before sharing changes. Build an optional local search index with `python3 scripts/wiki-search.py index`.
