---
name: wiki-search
description: "Find pages and sections in the wiki with the optional local search engine (keyword BM25, or hybrid keyword + semantic with Ollama). Also sets the search index up or reports its state. Use when the user says search the wiki, find pages about, where do we mention, which page covers, set up search, enable hybrid search, or search status."
allowed-tools: Bash(python3 scripts/wiki-search.py:*), Bash(python3 scripts/wiki-graph.py:*)
---

# wiki-search

`scripts/wiki-search.py` — standard-library Python, fully local. Optional: without it, the other
skills fall back to reading `index.md` files and Grep.

## Use it

```bash
python3 scripts/wiki-search.py query "<question or keywords>" [--domain <wiki> [--domain <wiki2>]] [--top 8] [--json]
```

- `--domain` takes a `wiki` value, folder or label from `.vault-meta/domains.json`; repeat it
  for two domains. Shared pages are always included. Without `--domain` the whole vault is
  searched — do that only when the user asks to search everything.
- Search finds **entry points**; the link graph gives context. After a hit, run
  `python3 scripts/wiki-graph.py neighbors "<Page>"` to see what it connects to.
- The header shows the mode: `[keyword]` (BM25 only) or `[hybrid]` (BM25 + embeddings, merged
  with reciprocal-rank fusion).
- The index refreshes itself when pages changed; in hybrid mode only changed sections are
  re-embedded.

Present results as a short list of `[[Page]] › section — one-line why`, then offer to answer
the question from them (wiki-query).

## Set it up / check it

| Level   | Needs                                           | Command                                                                            |
|---------|-------------------------------------------------|------------------------------------------------------------------------------------|
| keyword | `python3`                                       | `python3 scripts/wiki-search.py index`                                             |
| hybrid  | `python3` + Ollama running + `nomic-embed-text` | `ollama pull nomic-embed-text` then `python3 scripts/wiki-search.py index --embed` |
| status  | —                                               | `python3 scripts/wiki-search.py status`                                            |

Other models: set `WIKI_SEARCH_MODEL` (and `WIKI_SEARCH_OLLAMA_URL` for a non-default host),
then re-run `index --embed`. The index lives in `.vault-meta/search/` and is git-ignored: each
person builds their own. Never commit it.

If `index --embed` fails, report the message as-is (Ollama not running, or model not pulled) and
point to README › *Maintain the wiki*.
