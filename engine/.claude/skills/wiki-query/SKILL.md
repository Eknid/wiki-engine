---
name: wiki-query
description: "Answer a question from the wiki by navigating its structure: hub routing, domain hot cache and index, scoped search, then the [[link]] graph — ending with a route trace. Quick, standard and deep modes; files good answers back. Use when the user asks what do we know about, what is, how does, why did we, explain, summarize, compare, query:, query quick:, query deep:, or any question about the your wiki domains."
allowed-tools: Read, Glob, Grep, Bash(python3 scripts/wiki-search.py:*), Bash(python3 scripts/wiki-graph.py:*)
---

# wiki-query

Answer by **navigating the wiki's structure** — routing, catalogs, search, links — not by grepping
it. The structure is what makes answers cheap, complete and traceable. Routing: root `CLAUDE.md`.

**No question given?** (`/wiki-query` with nothing after it) Use the user's most recent question in
this conversation. Only if there is none, ask for one.

## Modes

| Mode         | Trigger                                                          | Route                                                |
|--------------|------------------------------------------------------------------|------------------------------------------------------|
| **Quick**    | `query quick: …`, a simple fact or date                          | steps 1–2 only; answer from hot/index, read no pages |
| **Standard** | default                                                          | steps 1–6, 3–5 pages, one graph expansion            |
| **Deep**     | `query deep: …`, "everything about", compare across the platform | steps 1–6, every relevant page, `--depth 2`          |

## The route — follow these steps in order, every time

1. **ROUTE.** Read root `wiki/index.md` (root `wiki/hot.md` is already in context from the
   SessionStart hook; Read it if it is not). Decide the **one or two** domains that own the
   question from the Domains table in `CLAUDE.md`, and note their `wiki` values
   (from `.vault-meta/domains.json`).
2. **ORIENT.** For each chosen domain, Read `<Domain>/wiki/hot.md` **and** `<Domain>/wiki/index.md`.
   In quick mode, stop here if they answer the question.
3. **FIND** 3–5 candidate pages:
   - the question **names a page** ("what relies on X", "what is X") → resolve it with
     `python3 scripts/wiki-graph.py resolve "<X>"` and go graph-first: X plus its neighbours
     (step 5) are the candidates;
   - otherwise, if `.vault-meta/search/index.json` exists:
     `python3 scripts/wiki-search.py query "<the question>" --domain <wiki> [--domain <wiki2>] --top 8`
     — always pass the domains from step 1;
   - otherwise take the candidates from the index lines read in step 2.
4. **READ** each candidate **in full with the Read tool** — never `head`, `sed` or `cut`.
5. **EXPAND** along the graph from the 1–2 most relevant pages:
   `python3 scripts/wiki-graph.py neighbors "<Page Name>"` (deep mode: `--depth 2`). The plain
   output is compact (one line per page); never truncate it.
   Read the neighbours the question needs: definitions, decisions, contradictions, the shared
   page. To open any `[[link]]`, resolve it with `python3 scripts/wiki-graph.py resolve "<Name>"`.
6. **ANSWER** (below), then the **route trace**.

**Grep and Glob are not discovery tools here.** Use Grep only to find an exact figure or term
inside a page already chosen in steps 3–5. Without `python3`: resolve links with Glob
`**/<Name>.md`, find backlinks with Grep for `[[<Name>` in `wiki/` and the domain `wiki/`
folders, and say `fallback: no python3` in the trace.

## Answer

- Lead with the answer, then the evidence. **Follow the length and format the user asked for**
  ("in 3 lines" means 3 lines; the trace line is extra).
- **No citations or `[[links]]` in the answer unless the user asks for sources.** The route trace
  already shows what was read. When sources are asked for, cite only pages you Read in this
  answer, by filename (a fact taken from a hot cache cites that hot cache, e.g.
  `[[Project A/wiki/hot|Project A hot cache]]`).
- When more than one domain contributes, say which fact comes from which.
- Surface any `> [!contradiction]` or `> [!gap]` on the pages you read.
- If the wiki does not cover it, say so and name the missing piece. Never answer from general
  knowledge as if it were the wiki's; offer to find and ingest a source.
- If the concept at the centre of the question has **no page of its own** and you had to assemble
  the answer from source summaries, say so in one line and suggest `/wiki-lint` (it lists such
  concepts under `missing-page` and creates the page through the wiki process). Do not create
  content pages during a query.
- **End with one trace line** of what you actually did, e.g.:

  `Route: hub index → Project A hot+index → search(project-a) → read: Example Concept → graph: Example Concept`

  If you skipped a step, say why (`quick: answered from hot.md`).

## Filing the answer back

Offer to file a standard answer; always file a deep one (unless the user said not to).

- Spans domains → `wiki/cross-domain/<Question as Title>.md`, `type: question`, `wiki: hub`,
  `used_in: [..]`, a "what each domain holds" table, `> [!contradiction]` where they disagree.
  Add it to root `wiki/index.md` (Cross-domain) and root `wiki/log.md`.
- One domain → `<Domain>/wiki/questions/<Question as Title>.md`, `wiki: <domain>`; add it to that
  domain's `index.md` and `log.md`.

Filed pages are wiki content, so they **do** link: `related:` lists every page read and the body
links the pages it relies on. Frontmatter (WIKI.md frontmatter section): `question:` as asked,
`answer_quality: draft|solid|definitive`.
