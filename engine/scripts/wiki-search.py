#!/usr/bin/env python3
"""wiki-search — optional hybrid search over the Wiki (standard library only).

Two levels, both optional:
  keyword  BM25 over page sections. Needs only python3.
  hybrid   BM25 + semantic similarity from a local Ollama embedding model, merged with
           reciprocal-rank fusion. Needs Ollama running with an embedding model pulled.

  python3 scripts/wiki-search.py index [--embed]            build or refresh the index
  python3 scripts/wiki-search.py query "topic" [--domain project-a] [--top 8] [--json]
  python3 scripts/wiki-search.py status

The index lives in .vault-meta/search/ (git-ignored) and refreshes itself on query when
pages changed. Embeddings are cached per chunk, so only new or edited sections are re-embedded.

Environment: WIKI_SEARCH_OLLAMA_URL (default http://localhost:11434),
             WIKI_SEARCH_MODEL (default nomic-embed-text).
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

import wikilib as W

DIR = W.ROOT / ".vault-meta" / "search"
INDEX = DIR / "index.json"
EMBED = DIR / "embeddings.json"
OLLAMA = os.environ.get("WIKI_SEARCH_OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("WIKI_SEARCH_MODEL", "nomic-embed-text")
VERSION = 1
MAX_CHARS = 1500
K1, B = 1.5, 0.75
RRF_K = 60
STOP = set("""a an and are as at be but by for from has have in into is it its of on or that the their this
to was were will with which what when where who why how not no can do does did than then there these those
we you they i our your all any each more most other some such only own same so too very just also about""".split())


# ── chunking ─────────────────────────────────────────────────────────────────────────────

def tokens(text: str) -> list:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9_\-\.]*[a-z0-9]|[a-z0-9]", text.lower()) if t not in STOP]


def searchable_pages():
    domains = W.load_domains()
    for p, kind in W.iter_files():
        if kind == "source" and W.wiki_of(p, domains) is not None or (kind == "source" and "/deliverables/" in p):
            yield p, domains


def chunk_page(p: str, domains: list) -> list:
    text = W.read(p)
    fm, body = W.split_frontmatter(text)
    fm = fm or {}
    title = fm.get("title") if isinstance(fm.get("title"), str) else p.rsplit("/", 1)[-1][:-3]
    wiki = W.wiki_of(p, domains) or (W.domain_of(p, domains) or {}).get("wiki", "hub")
    dom = W.domain_of(p, domains)
    label = dom["label"] if dom else ("Shared" if wiki == "shared" else "Hub")
    tags = " ".join(t.split("/")[-1] for t in (fm.get("tags") or []) if isinstance(t, str))
    sections, heading, buf = [], "", []
    for line in body.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if buf:
                sections.append((heading, "\n".join(buf)))
            heading, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf)))
    chunks = []
    for heading, sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        parts, cur = [], ""
        for para in re.split(r"\n\s*\n", sec):
            if len(cur) + len(para) > MAX_CHARS and cur:
                parts.append(cur); cur = ""
            cur = f"{cur}\n\n{para}" if cur else para
        if cur:
            parts.append(cur)
        for i, part in enumerate(parts):
            # Contextual prefix: domain › page › section, plus tags — so a short section still
            # carries where it lives and what it is about.
            prefix = f"{label} › {title}" + (f" › {heading}" if heading else "") + (f" ({tags})" if tags else "")
            full = f"{prefix}\n{part}"
            chunks.append({"path": p, "title": title, "wiki": wiki, "heading": heading, "part": i,
                           "sha": hashlib.sha1(full.encode("utf-8")).hexdigest(), "text": full})
    return chunks


# ── BM25 index ───────────────────────────────────────────────────────────────────────────

def fingerprint():
    return {p: os.stat(W.ROOT / p).st_mtime_ns for p, _ in searchable_pages()}


def build_index() -> dict:
    chunks = []
    for p, domains in searchable_pages():
        chunks.extend(chunk_page(p, domains))
    df = collections.Counter()
    for c in chunks:
        tf = collections.Counter(tokens(c["text"]))
        c["tf"], c["len"] = dict(tf), sum(tf.values())
        df.update(tf.keys())
    idx = {"version": VERSION, "built": datetime.datetime.now().isoformat(timespec="seconds"),
           "files": fingerprint(), "N": len(chunks), "avgdl": (sum(c["len"] for c in chunks) / max(len(chunks), 1)),
           "df": dict(df), "chunks": chunks}
    DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return idx


def load_index(refresh=True) -> dict:
    if INDEX.exists():
        idx = json.loads(INDEX.read_text(encoding="utf-8"))
        if idx.get("version") == VERSION and (not refresh or idx.get("files") == fingerprint()):
            return idx
    return build_index()


def bm25(idx: dict, query: str, allowed) -> list:
    q = tokens(query)
    N, avgdl, df = idx["N"], idx["avgdl"] or 1, idx["df"]
    scores = []
    for i, c in enumerate(idx["chunks"]):
        if allowed and c["wiki"] not in allowed:
            continue
        s = 0.0
        for t in q:
            f = c["tf"].get(t)
            if f:
                n = df.get(t, 0)
                idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
                s += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * c["len"] / avgdl))
        if s > 0:
            scores.append((s, i))
    return sorted(scores, reverse=True)


# ── embeddings (optional) ────────────────────────────────────────────────────────────────

def ollama_embed(texts: list) -> list:
    body = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA}/api/embed", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embeddings"]


def ollama_ok():
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            models = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
        return any(m == MODEL or m.startswith(MODEL + ":") for m in models), models
    except (urllib.error.URLError, OSError, ValueError):
        return False, None


def load_embeddings() -> dict:
    if EMBED.exists():
        e = json.loads(EMBED.read_text(encoding="utf-8"))
        if e.get("model") == MODEL:
            return e
    return {"model": MODEL, "vectors": {}}


def embed_index(idx: dict, quiet=False) -> int:
    emb = load_embeddings()
    todo = [c for c in idx["chunks"] if c["sha"] not in emb["vectors"]]
    for i in range(0, len(todo), 32):
        batch = todo[i:i + 32]
        # nomic-embed-text expects task prefixes; other models ignore them harmlessly.
        vecs = ollama_embed(["search_document: " + c["text"] for c in batch])
        for c, v in zip(batch, vecs):
            emb["vectors"][c["sha"]] = [round(x, 5) for x in v]
        if not quiet:
            print(f"  embedded {min(i + 32, len(todo))}/{len(todo)}", file=sys.stderr)
    live = {c["sha"] for c in idx["chunks"]}
    emb["vectors"] = {k: v for k, v in emb["vectors"].items() if k in live}
    DIR.mkdir(parents=True, exist_ok=True)
    EMBED.write_text(json.dumps(emb), encoding="utf-8")
    return len(todo)


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ── query ────────────────────────────────────────────────────────────────────────────────

def resolve_domain(value: str, domains: list):
    v = value.strip().lower()
    for d in domains:
        if v in (d["wiki"], d["folder"].lower(), d["label"].lower()):
            return {d["wiki"]}
    if v in ("hub", "shared"):
        return {v}
    sys.exit(f"unknown domain '{value}'. Use one of: " + ", ".join(d["wiki"] for d in domains) + ", hub, shared")


def query(text: str, domain=None, top=8, mode="auto") -> dict:
    domains = W.load_domains()
    idx = load_index()
    # Scope = the domains chosen by routing, plus shared pages. No --domain = the whole vault.
    allowed = set().union(*(resolve_domain(d, domains) for d in domain)) | {"shared"} if domain else None
    lexical = bm25(idx, text, allowed)

    used = "keyword"
    semantic = []
    if mode != "keyword" and EMBED.exists():
        ok, _ = ollama_ok()
        if ok:
            emb = load_embeddings()
            missing = [c for c in idx["chunks"] if c["sha"] not in emb["vectors"]]
            if missing:
                embed_index(idx, quiet=True)
                emb = load_embeddings()
            qv = ollama_embed(["search_query: " + text])[0]
            for i, c in enumerate(idx["chunks"]):
                if allowed and c["wiki"] not in allowed:
                    continue
                v = emb["vectors"].get(c["sha"])
                if v:
                    semantic.append((cosine(qv, v), i))
            semantic.sort(reverse=True)
            used = "hybrid"

    # Reciprocal-rank fusion: robust to the different score scales of BM25 and cosine.
    fused = collections.defaultdict(float)
    for rank, (_, i) in enumerate(lexical[:100]):
        fused[i] += 1.0 / (RRF_K + rank + 1)
    for rank, (_, i) in enumerate(semantic[:100]):
        fused[i] += 1.0 / (RRF_K + rank + 1)

    by_page = {}
    for i, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True):
        c = idx["chunks"][i]
        if c["path"] not in by_page:
            body = c["text"].split("\n", 1)[-1]
            snippet = re.sub(r"\s+", " ", body).strip()[:240]
            by_page[c["path"]] = {"path": c["path"], "title": c["title"], "wiki": c["wiki"],
                                  "section": c["heading"], "score": round(score, 5), "snippet": snippet}
        if len(by_page) >= top:
            break
    return {"query": text, "mode": used, "domain": domain, "results": list(by_page.values())}


# ── cli ──────────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index", help="build or refresh the index")
    pi.add_argument("--embed", action="store_true", help="also compute embeddings with Ollama (hybrid mode)")
    pq = sub.add_parser("query", help="search the vault")
    pq.add_argument("text")
    pq.add_argument("--domain", action="append",
                    help="limit to a domain (wiki value, folder or label); repeat for two domains; shared pages always included")
    pq.add_argument("--top", type=int, default=8)
    pq.add_argument("--keyword", action="store_true", help="skip the semantic part even if embeddings exist")
    pq.add_argument("--json", action="store_true")
    sub.add_parser("status", help="show index and Ollama state")
    a = ap.parse_args()

    if a.cmd == "index":
        idx = build_index()
        print(f"keyword index: {idx['N']} sections from {len(idx['files'])} pages → {W.rel(INDEX)}")
        if a.embed:
            ok, models = ollama_ok()
            if not ok:
                sys.exit(f"Ollama not reachable at {OLLAMA} or model '{MODEL}' not pulled "
                         f"(found: {models}). Run: ollama pull {MODEL}")
            n = embed_index(idx)
            print(f"semantic index: embedded {n} new sections with {MODEL} → {W.rel(EMBED)}")
        return 0

    if a.cmd == "status":
        if not INDEX.exists():
            print("no index yet — run: python3 scripts/wiki-search.py index")
            return 0
        idx = json.loads(INDEX.read_text(encoding="utf-8"))
        fresh = idx.get("files") == fingerprint()
        emb = load_embeddings() if EMBED.exists() else {"vectors": {}}
        covered = sum(1 for c in idx["chunks"] if c["sha"] in emb["vectors"])
        ok, models = ollama_ok()
        print(f"keyword index : {idx['N']} sections, built {idx['built']}, {'fresh' if fresh else 'stale (refreshes on next query)'}")
        print(f"semantic index: {covered}/{idx['N']} sections embedded with {emb.get('model', MODEL)}" if EMBED.exists()
              else "semantic index: not set up (optional) — see README › Optional: hybrid search")
        print(f"ollama        : {'ready' if ok else 'not reachable / model missing'} at {OLLAMA} (model {MODEL})")
        return 0

    res = query(a.text, a.domain, a.top, "keyword" if a.keyword else "auto")
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    print(f"[{res['mode']}] {a.text}" + (f"  (scope: {' + '.join(a.domain)} + shared)" if a.domain else "  (scope: whole vault)"))
    for n, r in enumerate(res["results"], 1):
        sec = f" › {r['section']}" if r["section"] else ""
        print(f"{n}. {r['path']}{sec}\n   {r['snippet']}")
    if not res["results"]:
        print("no matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
