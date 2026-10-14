"""Shared helpers for the Wiki scripts (standard library only, Python 3.8+).

Used by wiki-check.py and wiki-search.py. Knows the vault layout: the hub wiki at the
root, the domain sub-wikis registered in .vault-meta/domains.json, and which files are
pages, which are system files, and how Obsidian resolves a [[wikilink]].
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("WIKI_ROOT", Path(__file__).resolve().parent.parent)).resolve()

# Folders never scanned as content.
SKIP_DIRS = {".git", ".obsidian", ".claude", ".github", ".trash", "node_modules", "__pycache__", ".vault-meta", "wiki-engine", "wiki-engine-repo"}
# Folders scanned for link *targets* only (they exist, but are not checked as link sources).
TARGET_ONLY_DIRS = {".raw", "_templates", "Clippings"}
# Read by path, never linked; may repeat across domains.
SYSTEM_NAMES = {"index", "hot", "log", "overview", "_index", "dashboard", "claude", "wiki", "readme"}

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
FENCE_RE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]\n]+?)\]\]")


def load_domains() -> list:
    with open(ROOT / ".vault-meta" / "domains.json", encoding="utf-8") as f:
        return json.load(f)["domains"]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def wiki_of(relpath: str, domains: list) -> str | None:
    """Expected `wiki:` value for a file, or None when the file is not a wiki page."""
    parts = relpath.split("/")
    if parts[0] == "wiki":
        return "shared" if len(parts) > 2 and parts[1] == "shared" else "hub"
    for d in domains:
        if parts[0] == d["folder"] and len(parts) > 2 and parts[1] == "wiki":
            return d["wiki"]
    return None


def domain_of(relpath: str, domains: list) -> dict | None:
    first = relpath.split("/")[0]
    return next((d for d in domains if d["folder"] == first), None)


def iter_files():
    """Yield (relpath, kind) for every file in the vault. kind: 'source' (checked) or 'target'."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        d = Path(dirpath)
        r = "" if d == ROOT else rel(d)
        dirnames[:] = sorted(x for x in dirnames if x not in SKIP_DIRS)
        target_only = any(part in TARGET_ONLY_DIRS for part in r.split("/") if part)
        for name in sorted(filenames):
            if name.startswith(".") and name != ".gitkeep":
                continue
            relpath = f"{r}/{name}" if r else name
            kind = "target" if target_only or not name.endswith(".md") else "source"
            yield relpath, kind


def read(relpath: str) -> str:
    with open(ROOT / relpath, encoding="utf-8", errors="replace") as f:
        return f.read()


def split_frontmatter(text: str):
    """Return (frontmatter dict, body). Parses the flat YAML used in this vault."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    fm, key = {}, None
    for line in m.group(1).split("\n"):
        km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                fm[key] = [v.strip().strip("\"'") for v in re.findall(r'"[^"]*"|\'[^\']*\'|[^,\[\]]+', val[1:-1]) if v.strip()]
            elif val == "":
                fm[key] = []
            else:
                fm[key] = val.strip("\"'")
        elif key and re.match(r"^\s+-\s*", line) and isinstance(fm.get(key), list):
            fm[key].append(re.sub(r"^\s+-\s*", "", line).strip().strip("\"'"))
    return fm, text[m.end():]


def strip_code(text: str) -> str:
    """Remove fenced blocks and inline code, where Obsidian does not render links."""
    return INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))


def extract_links(text: str) -> list:
    """Return [(target, heading, is_embed)] for every [[wikilink]] outside code."""
    out = []
    for m in WIKILINK_RE.finditer(strip_code(text)):
        inner = re.split(r"\\?\|", m.group(2), maxsplit=1)[0]
        target, _, heading = inner.partition("#")
        target = target.strip()
        if target.startswith("^"):
            continue
        out.append((target, heading.strip(), m.group(1) == "!"))
    return out


class Resolver:
    """Resolve link targets the way Obsidian does: by unique name, or by path suffix."""

    def __init__(self, relpaths):
        self.by_name, self.by_path = {}, {}
        for p in relpaths:
            stem = p[:-3] if p.endswith(".md") else p
            name = stem.rsplit("/", 1)[-1]
            keys = {name.lower()} | ({p.rsplit("/", 1)[-1].lower()} if not p.endswith(".md") else set())
            for k in keys:
                self.by_name.setdefault(k, []).append(p)
            self.by_path[stem.lower()] = p
            self.by_path[p.lower()] = p

    def resolve_from(self, target: str, source: str | None = None) -> list:
        """Resolve one link as Obsidian does from `source`: a repeated name (index, hot, overview…)
        resolves to the copy in the source's own top-level folder."""
        hits = self.resolve(target)
        if len(hits) > 1:
            top = (source or "").split("/")[0]
            # Obsidian does not index dot-folders (.raw/), so a bare name prefers the visible page;
            # then the copy in the source's own top-level folder.
            hits = sorted(hits, key=lambda h: (is_hidden(h), h.split("/")[0] != top, h))
            return hits[:1]
        return hits

    def resolve(self, target: str):
        t = target.strip().lower()
        if t.endswith(".md"):
            t = t[:-3]
        if "/" in t:
            if t in self.by_path:
                return [self.by_path[t]]
            hits = [p for k, p in self.by_path.items() if k.endswith("/" + t)]
            return sorted(set(hits))
        return self.by_name.get(t, [])


def is_hidden(path: str) -> bool:
    """True for files inside a dot-folder such as .raw/ (invisible to Obsidian's link index)."""
    return any(part.startswith(".") for part in path.split("/")[:-1])


CATALOG_NAMES = {"index", "_index", "hot", "log", "overview", "dashboard"}


def is_catalog(path: str) -> bool:
    """Navigation pages that link to many others: index, _index, hot, log, overview, dashboards,
    anything in meta/, and pages named '… Index' (e.g. 'Streaming Engine Build — Task Index')."""
    stem = path.rsplit("/", 1)[-1]
    stem = stem[:-3] if stem.endswith(".md") else stem
    return stem.lower() in CATALOG_NAMES or stem.lower().endswith(" index") or "/meta/" in path


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))
