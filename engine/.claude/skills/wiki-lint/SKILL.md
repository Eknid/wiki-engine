---
name: wiki-lint
description: "Health-check the wiki: broken links, duplicate names, frontmatter and wiki: errors, oversized hot caches, shared-page drift, promotion candidates, orphans, stale claims and missing cross-references. Runs scripts/wiki-check.py when python3 is available, adds the judgement checks a script cannot do, writes a lint report, and offers fixes. Use when the user says lint, health check, check the wiki, wiki audit, clean up the wiki, find orphans or find broken links."
allowed-tools: Bash(python3 scripts/wiki-check.py:*), Bash(python3 scripts/wiki-graph.py:*)
---

# wiki-lint

Two layers: **deterministic checks** (exact, done by `scripts/wiki-check.py`) and **judgement
checks** (done by you, reading pages). Page rules: `WIKI.md`.

## 1. Deterministic checks

If `python3` is available:

```bash
python3 scripts/wiki-check.py --report wiki/meta/lint-report-$(date +%F).md
```

It finds: duplicate names, missing `type`/`wiki`, `wiki:` values that do not match the folder,
broken links (marking **new** ones vs `.vault-meta/lint-baseline.json`), `hot.md` over 500
words, shared pages whose `used_in` and `## In <Domain>` sections disagree, unregistered
domain folders, promotion candidates (domain pages linked from another domain), orphans, and
pages missing from their domain catalog. For broken links that name a page **title** instead of
a filename it prints the exact fix.

Without `python3`, do the same checks yourself with Glob and Grep: list every `.md` under
`wiki/` and `<Domain>/wiki/`, extract `[[targets]]` outside code, and compare against
filenames. Say in the report that it was a manual pass.

## 2. Judgement checks

Read the domain `hot.md`, `index.md` and the pages the script flagged, then look for:

- **Stale claims:** statements a newer source or log entry has overtaken (`> [!stale]`).
- **Missing pages:** review the script's `missing-page` candidates (concepts mentioned on many
  pages with no page of their own; the list is deliberately generous). Keep the real concepts
  (e.g. *important concept*), drop generic phrases (e.g. *row counts*, *last event*).
- **Missing cross-references:** a page mentions an existing page's name without linking it.
- **Unflagged conflicts:** two pages that disagree with no `> [!contradiction]` on either.
- **Pages over 300 lines** that cover two ideas and should split.
- **Promotion:** for each promotion candidate, run `python3 scripts/wiki-graph.py neighbors
  "<Page>"` and decide whether the other domain truly *needs* the page (several pages rely on
  it → promote per WIKI.md navigation and maintenance section) or just mentions it once (leave it).
- **Orphans:** for each orphan, `wiki-graph.py neighbors --depth 2` on its closest page shows
  where it belongs; suggest the link.

## 3. Report and fix

1. Append the judgement findings to the report file, under a `## Judgement checks` section.
2. Summarise in chat: errors first, then new broken links, then the rest.
3. Apply fixes requested by the user:
   - title links → use the suggested `[[path|Title]]` replacements from the report;
   - **create a missing page** — the wiki process for new content, not a hand-written page:
     1. name it in Title Case, singular (`Feature Group`); check it is unused with
        `python3 scripts/wiki-graph.py resolve "<Name>"`;
     2. place it by the promotion rule: used by 2+ domains → `wiki/shared/` with an
        `## In <Label>` section per domain; one domain → that domain's `concepts/` or `entities/`;
     3. build it **only from the vault**: search for the phrase, Read the 3–6 pages that say the
        most about it, and synthesise; every claim keeps a `sources:` / `[[link]]` to those pages;
        unknowns become `> [!gap]`, disagreements `> [!contradiction]`;
     4. link it in: turn the first unlinked mention on each of those pages into `[[Name]]`, and add
        it to the right `index.md` (root index for shared pages);
     5. log it (`## [date] lint | created [[Name]] from N pages`) and refresh the matching `hot.md`;
   - promotions, stubs, cross-links, `> [!stale]` / `> [!contradiction]` callouts → edit pages.
4. After fixing, re-run the check. If the remaining broken links are accepted as known, refresh
   the CI baseline: `python3 scripts/wiki-check.py --update-baseline` (commit the baseline by hand).
5. Log the run at the top of root `wiki/log.md` (`## [date] lint | …`).
