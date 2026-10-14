#!/usr/bin/env python3
"""wiki-graph — navigate the [[link]] graph of the Wiki (standard library only).

  python3 scripts/wiki-graph.py resolve "Page Name"                 name → file
  python3 scripts/wiki-graph.py neighbors "Page Name" [--depth 2]   links out, backlinks, 2nd hop
  python3 scripts/wiki-graph.py path "Page A" "Page B"              shortest link chain

A page can be given as a name, a [[wikilink]] (alias and heading are ignored) or a vault path.
Add --json for machine-readable output (what the skills use).

Catalog pages (index.md, _index.md, hot.md, log.md, overview.md) link to almost everything, so
they are reported separately as "listed in" and never used to build paths or second hops.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys

import wikilib as W

META_DOCS = {"README.md", "CLAUDE.md", "WIKI.md", "MIGRATION-STRATEGY.md"}


def stem(p: str) -> str:
    return p.rsplit("/", 1)[-1][:-3] if p.endswith(".md") else p.rsplit("/", 1)[-1]


def is_catalog(p: str) -> bool:
    return W.is_catalog(p)


def is_meta_doc(p: str) -> bool:
    return p.rsplit("/", 1)[-1] in META_DOCS


class Graph:
    def __init__(self):
        self.domains = W.load_domains()
        files = list(W.iter_files())
        self.resolver = W.Resolver([p for p, _ in files])
        self.nodes, self.out, self.inn, self.broken = {}, collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
        for p, kind in files:
            if kind != "source" or is_meta_doc(p):
                continue
            text = W.read(p)
            fm, _ = W.split_frontmatter(text)
            title = (fm or {}).get("title")
            self.nodes[p] = {"path": p, "name": stem(p), "title": title if isinstance(title, str) else stem(p),
                             "wiki": W.wiki_of(p, self.domains) or ((W.domain_of(p, self.domains) or {}).get("wiki", "hub"))}
            for target, _h, _e in W.extract_links(text):
                if not target:
                    continue
                hits = self.resolver.resolve_from(target, p)
                if not hits:
                    self.broken[p].add(target)
                for h in hits:
                    if h != p and h.endswith(".md"):
                        self.out[p].add(h)
                        self.inn[h].add(p)

    def find(self, query: str) -> list:
        q = re.sub(r"^\[\[|\]\]$", "", query.strip())
        q = re.split(r"\\?\|", q, maxsplit=1)[0].split("#", 1)[0].strip()
        hits = [h for h in self.resolver.resolve(q) if h in self.nodes]
        if hits:
            return hits
        ql = q.lower()  # fall back to title match
        return [p for p, n in self.nodes.items() if n["title"].lower() == ql]

    def one(self, query: str) -> str:
        hits = self.find(query)
        if not hits:
            sys.exit(f"no page named '{query}'. Try: python3 scripts/wiki-search.py query \"{query}\"")
        if len(hits) > 1:
            sys.exit(f"'{query}' is ambiguous ({len(hits)} pages); pass a path:\n  " + "\n  ".join(hits))
        return hits[0]

    def content(self, ps):
        return sorted(p for p in ps if p in self.nodes and not is_catalog(p))

    def info(self, p: str) -> dict:
        n = self.nodes[p]
        return {"name": n["name"], "path": p, "wiki": n["wiki"]}

    def neighbors(self, p: str, depth: int = 1) -> dict:
        out, inn = self.content(self.out[p]), self.content(self.inn[p])
        res = {"page": self.info(p), "title": self.nodes[p]["title"],
               "links_to": [self.info(x) for x in out],
               "linked_from": [self.info(x) for x in inn],
               "listed_in": sorted(x for x in self.inn[p] if is_catalog(x)),
               "broken": sorted(self.broken[p])}
        if depth >= 2:
            first = set(out) | set(inn)
            hops = collections.Counter()
            for f in first:
                for x in self.content(self.out[f] | self.inn[f]):
                    if x != p and x not in first:
                        hops[x] += 1
            res["second_hop"] = [dict(self.info(x), via=c) for x, c in hops.most_common(15)]
        return res

    def path(self, a: str, b: str):
        """Shortest undirected chain between two content pages (catalog pages excluded)."""
        prev, queue = {a: None}, collections.deque([a])
        while queue:
            cur = queue.popleft()
            if cur == b:
                chain = []
                while cur:
                    chain.append(cur); cur = prev[cur]
                return chain[::-1]
            for x in self.content(self.out[cur] | self.inn[cur]):
                if x not in prev:
                    prev[x] = cur; queue.append(x)
        return None


def show(items, indent="  "):
    return "\n".join(f"{indent}- {i['name']}  ·  {i['path']}  [{i['wiki']}]" + (f"  (via {i['via']})" if "via" in i else "")
                     for i in items) or f"{indent}(none)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="name or [[link]] → file path(s)")
    r.add_argument("page")
    r.add_argument("--json", action="store_true")
    n = sub.add_parser("neighbors", help="links out, backlinks and (with --depth 2) second-hop pages")
    n.add_argument("page")
    n.add_argument("--depth", type=int, choices=(1, 2), default=1)
    n.add_argument("--json", action="store_true")
    pa = sub.add_parser("path", help="shortest link chain between two pages")
    pa.add_argument("a")
    pa.add_argument("b")
    pa.add_argument("--json", action="store_true")
    args = ap.parse_args()
    g = Graph()

    if args.cmd == "resolve":
        hits = g.find(args.page)
        data = [g.info(h) for h in hits]
        print(json.dumps(data, indent=1, ensure_ascii=False) if args.json else
              ("\n".join(f"{d['path']}  [{d['wiki']}]" for d in data) or f"no page named '{args.page}'"))
        return 0 if hits else 1

    if args.cmd == "neighbors":
        res = g.neighbors(g.one(args.page), args.depth)
        if args.json:
            print(json.dumps(res, indent=1, ensure_ascii=False))
            return 0
        pg = res["page"]
        print(f"{pg['name']}  ·  {pg['path']}  [{pg['wiki']}]")
        print(f"→ links to ({len(res['links_to'])}):\n{show(res['links_to'])}")
        print(f"← linked from ({len(res['linked_from'])}):\n{show(res['linked_from'])}")
        if res["listed_in"]:
            print(f"☰ listed in: {', '.join(res['listed_in'])}")
        if res["broken"]:
            print(f"✗ broken links: {', '.join('[[' + b + ']]' for b in res['broken'])}")
        if "second_hop" in res:
            print(f"⇢ second hop (top {len(res['second_hop'])}, ranked by first-hop connections):\n{show(res['second_hop'])}")
        return 0

    a, b = g.one(args.a), g.one(args.b)
    chain = g.path(a, b)
    if args.json:
        print(json.dumps([g.info(x) for x in chain] if chain else None, indent=1, ensure_ascii=False))
    elif chain:
        print(f"{len(chain) - 1} hops:\n" + "\n".join(f"  {'↳ ' if i else ''}{g.nodes[x]['name']}  [{g.nodes[x]['wiki']}]" for i, x in enumerate(chain)))
    else:
        print("no link path between them (outside catalog pages)")
    return 0 if chain else 1


if __name__ == "__main__":
    sys.exit(main())
