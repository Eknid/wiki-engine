---
name: wiki-save
description: "Save an answer, analysis, decision or insight from the current conversation into the wiki as a proper page in the right domain (or cross-domain), with frontmatter, links, and index, log and hot updates. Use when the user says save this, save that answer, file this, keep this, add this to the wiki, save this analysis, or record this decision."
allowed-tools: Bash(python3 scripts/wiki-graph.py:*)
---

# wiki-save

Turn what was worked out in chat into a page, so it is not lost. Page format: `WIKI.md`.

## Steps

1. **Pick the content.** Identify the part of the conversation worth keeping. If unclear, ask
   which part, and for a short title.
2. **Pick the place.** Use the routing in `CLAUDE.md`:

   | Content                              | Folder                     | `type:`    |
   |--------------------------------------|----------------------------|------------|
   | answer spanning two or more domains  | `wiki/cross-domain/`       | `question` |
   | answer or analysis within one domain | `<Domain>/wiki/questions/` | `question` |
   | a decision that was made or proposed | `<Domain>/wiki/decisions/` | `decision` |
   | an explained idea or pattern         | `<Domain>/wiki/concepts/`  | `concept`  |
   | a design or plan (research domains)  | `<Domain>/wiki/designs/`   | `design`   |

   Check the name is unused anywhere in the vault: `python3 scripts/wiki-graph.py resolve "<Title>"`
   (without python: Glob `**/<Title>.md`). If it exists, **ask** whether to extend that page
   instead. Link the new page to the pages the conversation relied on, and check what they
   connect to with `wiki-graph.py neighbors` so the page lands in the right neighbourhood.
3. **Write it** in declarative present tense — the content itself, not "the user asked". Use
   the domain template, set `wiki:` (`hub` for cross-domain), `related:` every page mentioned,
   and cite sources. Keep `> [!gap]` and `> [!contradiction]` where the conversation left
   things open.
4. **Record:** add a line to the right `index.md` (domain, or root for cross-domain), a new
   entry at the top of the matching `log.md` (`## [date] save | Title`), and refresh that
   `hot.md`.
5. **Confirm** with the link: "Saved as [[Title]] in `<folder>`."
