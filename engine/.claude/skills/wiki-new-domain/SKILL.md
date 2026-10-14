---
name: wiki-new-domain
description: "Add a domain to this wiki: create its folders, catalogs, templates, and registry entry. Use for new sub-wikis or domains."
disable-model-invocation: true
---

# wiki-new-domain

Use `CLAUDE.md` and `.vault-meta/domains.json` to choose a distinct scope. Obtain a folder name, a kebab-case `wiki` value, a short label, and a one-line scope from the request or ask if genuinely missing.

Create `<Domain>/.raw/{articles,transcripts,data,assets}/`, `<Domain>/_attachments/`, `<Domain>/_templates/`, `<Domain>/deliverables/`, and `<Domain>/wiki/{sources,entities,concepts,comparisons,questions,decisions,meta}/`. Put `.gitkeep` in empty directories. Copy the generic templates from an existing domain and change `wiki:`. Create `wiki/index.md`, `hot.md`, `log.md`, and `overview.md` with the new `wiki:` value and the format in `WIKI.md`.

Add `{folder, wiki, label, prefix, scope}` to `.vault-meta/domains.json`. Update the Domains table in root `CLAUDE.md`, root `wiki/index.md`, and add a root `wiki/log.md` entry. Run `python3 scripts/wiki-check.py --ci` and fix new errors.
