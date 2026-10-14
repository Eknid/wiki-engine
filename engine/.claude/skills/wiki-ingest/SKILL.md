---
name: wiki-ingest
description: "Ingest a source into the wiki: route it to the right domain, read it fully, and create or update the source, entity and concept pages, plus index, log and hot cache. Handles files in <Domain>/.raw/ or Clippings/, pasted text, URLs, images, and batches. Use when the user says ingest, process this source, add this to the wiki, file this document, batch ingest, ingest all of these, or ingest <url>."
allowed-tools: Bash(python3 scripts/wiki-search.py:*), Bash(python3 scripts/wiki-graph.py:*), Bash(python3 scripts/wiki-check.py)
---

# wiki-ingest

Read the source. Write the wiki. Link everything. One source typically touches 8–15 pages.
Page format: `WIKI.md`. Routing rules: root `CLAUDE.md`. Domain registry: `.vault-meta/domains.json`.

## 1. Locate and route

1. Find the source:
   - a path in `<Domain>/.raw/…` → the domain is given;
   - a file in `Clippings/` or anywhere else → route it (step 2), then **move** it to
     `<Domain>/.raw/<articles|transcripts|data|assets>/` with `git mv` (or `mv` if untracked);
   - a URL → fetch with WebFetch, save the cleaned text to `<Domain>/.raw/articles/<slug>-<YYYY-MM-DD>.md`
     with frontmatter `source_url:` and `fetched:`;
   - an image → Read it, transcribe text and describe diagrams into
     `<Domain>/.raw/assets/<slug>-<YYYY-MM-DD>.md`, copy the image to `<Domain>/_attachments/`;
   - pasted text → save it to `<Domain>/.raw/data/<slug>-<YYYY-MM-DD>.md` first.
2. Route with the table and tie-breakers in `CLAUDE.md`. Say which domain you picked and why in
   one line. **If two domains fit equally, ask** before writing anything.
3. Skip unchanged sources: if `<Domain>/wiki/log.md` already records an ingest of this exact
   file and its git history shows no change since, report "already ingested" unless the user
   said *force* or *re-ingest*.

From here on, "the domain" means `<Domain>/`; every path below is inside it unless it starts
with root `wiki/`.

## 2. Read before writing

1. Read the source **completely**. Do not skim.
2. Read root `wiki/hot.md`, then `<Domain>/wiki/hot.md` and `<Domain>/wiki/index.md`.
3. Find existing pages for every entity and concept you are about to write — across **all
   domains and `wiki/shared/`**, because names are unique vault-wide (this is the one
   deliberately vault-wide lookup):
   - exact name: `python3 scripts/wiki-graph.py resolve "<Name>"` → the page and its sub-wiki;
   - related pages under other names: `python3 scripts/wiki-search.py query "<topic>" --top 5`
     (if the search index exists);
   - before linking a new page into the domain, see what the closest existing page connects to:
     `python3 scripts/wiki-graph.py neighbors "<Page>"`.
   Without `python3`: Glob `**/<Name>.md` and Grep for the topic.
4. Share 3–5 key takeaways and use the stated user priorities when writing.

## 3. Write

Use `<Domain>/_templates/<type>.md` and `WIKI.md` §3 for frontmatter. Always set `wiki:` to the
domain's value from `domains.json`.

1. **Source page** in `wiki/sources/` (or `wiki/papers/` for academic papers in a research
   domain): summary, key claims, what is new, `sources:` pointing at the raw file.
2. **Entities and concepts**, one page each, for every significant product, service, org,
   person, idea or pattern:
   - exists in **this** domain → update it, add the new facts with citations;
   - exists in **another** domain (`resolve` shows a different `wiki`) → this is the second
     domain needing it: **promote** it
     (step 4) instead of creating a copy;
   - exists in `wiki/shared/` → add or extend this domain's `## In <Label>` section;
   - nowhere → create it in this domain. If its natural name is generic (Tech Stack, Data
     Flow, …), prefix it with the domain's `prefix` from `domains.json`.
3. Domain hub pages (overview, `_index.md` sub-catalogs, decision or flow pages) when the
   source changes them.
4. **Promotion to shared** (WIKI.md navigation and maintenance section): `git mv` the page to `wiki/shared/<same name>.md`,
   restructure as generic intro + `## In <Label>` per domain, set `wiki: shared` and
   `used_in`, merge in any facts from other copies, delete the copies. Links keep working
   because the filename is unchanged.
5. **Contradictions:** when the source conflicts with a page, add `> [!contradiction]` to
   **both** the existing page and the new source page, naming both sides. Never silently
   overwrite an old claim. If the conflict spans domains, also note it in root `wiki/hot.md`.

## 4. Record

1. `<Domain>/wiki/index.md`: one line per new page in the right section.
2. `<Domain>/wiki/log.md`: new entry **at the top** (format in WIKI.md navigation and maintenance section).
3. `<Domain>/wiki/hot.md`: rewrite it with this ingest's context (under 500 words).
4. Root `wiki/index.md` and `wiki/log.md` only if you created or changed a shared page.
5. Run `python3 scripts/wiki-check.py` if `python3` exists and fix any **new** error or broken
   link you introduced. Without python, Grep your new links against existing filenames.
6. Report: domain, pages created, pages updated, promotions, contradictions, open gaps.

Commit and push according to the host repository's workflow.

## 5. Batch ingest

1. List the files and the domain for each.
2. For more than 3 sources, dispatch one `wiki-ingest-worker` subagent per source, in
   parallel, with the source path and domain. Workers create only **new** pages and return the
   updates they want on existing pages.
3. You alone apply those updates, promotions, index, log and hot changes — one writer for
   shared files means no conflicts.
4. Cross-reference pass across the new sources, then one log entry and one hot.md rewrite for
   the batch.
5. Check in with the user every 10 sources.

## Never

- Edit anything in `.raw/` after it lands (moving a clip into `.raw/` is fine).
- Create a page whose name already exists anywhere in the vault.
- Put domain pages in the root `wiki/` (it holds hub, shared and cross-domain content only).
- Skip the log entry or the hot.md update.
- Read more than 3–5 existing pages per source unless the user asked for depth.
