#!/usr/bin/env python3
"""wiki-check — deterministic health checks for the Wiki.

Standard library only. Used by the wiki-lint skill and by CI.

  python3 scripts/wiki-check.py                  # markdown report on stdout
  python3 scripts/wiki-check.py --json           # machine-readable findings
  python3 scripts/wiki-check.py --report FILE    # also write the markdown report to FILE
  python3 scripts/wiki-check.py --ci             # exit 1 on errors or on broken links not in the baseline
  python3 scripts/wiki-check.py --update-baseline

Severities
  error    duplicate page names, missing/invalid frontmatter on wiki pages, wrong `wiki:` value,
           and (with --ci) broken links that are not in .vault-meta/lint-baseline.json
  warning  broken links, hot.md over 500 words, shared pages whose `used_in` and
           `## In <Domain>` sections disagree, unregistered domain folders
  info     promotion candidates (domain pages linked from another domain), missing pages
           (concepts mentioned on many pages with no page of their own), orphan pages,
           pages missing from their domain's catalog
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import re
import sys

import wikilib as W

BASELINE = W.ROOT / ".vault-meta" / "lint-baseline.json"
HOT_LIMIT = 500


def scan():
    domains = W.load_domains()
    files = list(W.iter_files())
    resolver = W.Resolver([p for p, _ in files])
    pages = {}
    for p, kind in files:
        if kind != "source":
            continue
        text = W.read(p)
        fm, body = W.split_frontmatter(text)
        pages[p] = {"fm": fm, "body": body, "links": W.extract_links(text), "wiki": W.wiki_of(p, domains)}
    return domains, files, resolver, pages


def title_index(pages):
    """title (lowercase) -> [paths], for links written against a page's title instead of its file name."""
    t = collections.defaultdict(list)
    for p, info in pages.items():
        title = (info["fm"] or {}).get("title")
        if isinstance(title, str) and title:
            t[title.lower()].append(p)
    return t


def suggest_for(page, target, titles, domains):
    """If [[target]] names a page title, return the path link that resolves: same domain first."""
    hits = titles.get(target.lower(), [])
    near = [h for h in hits if h.split("/")[0] == page.split("/")[0]]
    pick = near or (hits if len(hits) == 1 else [])
    return pick[0][:-3] if pick else None


def check(domains, files, resolver, pages):
    F = collections.defaultdict(list)  # check name -> list of findings
    labels = {d["wiki"]: d["label"] for d in domains}
    titles = title_index(pages)

    # Unregistered domain folders: top-level folders with a wiki/index.md that domains.json does not know.
    registered = {d["folder"] for d in domains}
    for p, _ in files:
        parts = p.split("/")
        if len(parts) == 3 and parts[1:] == ["wiki", "index.md"] and parts[0] not in registered:
            F["unregistered-domain"].append({"severity": "warning", "page": parts[0],
                                             "detail": "has wiki/index.md but is not in .vault-meta/domains.json"})

    # Duplicate names (Obsidian resolves [[Name]] to one file only).
    by_name = collections.defaultdict(list)
    for p, _ in files:
        if p.endswith(".md") and "/_templates/" not in f"/{p}" and "/.raw/" not in f"/{p}":
            by_name[p.rsplit("/", 1)[-1][:-3].lower()].append(p)
    for name, ps in sorted(by_name.items()):
        if len(ps) > 1 and name not in W.SYSTEM_NAMES:
            F["duplicate-name"].append({"severity": "error", "page": name, "detail": ps})

    inbound = collections.defaultdict(set)
    broken = []
    for p, info in pages.items():
        expected = info["wiki"]
        if expected:  # a wiki page
            fm = info["fm"]
            if fm is None:
                F["frontmatter"].append({"severity": "error", "page": p, "detail": "no frontmatter"})
            else:
                missing = [k for k in ("type", "wiki") if not fm.get(k)]
                if missing:
                    F["frontmatter"].append({"severity": "error", "page": p, "detail": f"missing: {', '.join(missing)}"})
                elif fm["wiki"] != expected:
                    F["wiki-value"].append({"severity": "error", "page": p,
                                            "detail": f"wiki: {fm['wiki']} but the page lives in '{expected}'"})
        for target, _heading, _embed in info["links"]:
            if not target:
                continue
            hits = resolver.resolve_from(target, p)
            if not hits:
                broken.append({"page": p, "target": target, "suggest": suggest_for(p, target, titles, domains)})
            for h in hits:
                if h != p:
                    inbound[h].add(p)

    baseline = set()
    if BASELINE.exists():
        baseline = {(b["page"], b["target"]) for b in json.loads(BASELINE.read_text(encoding="utf-8"))["broken_links"]}
    for b in broken:
        b["known"] = (b["page"], b["target"]) in baseline
        detail = f"[[{b['target']}]]" + (f" → title of `{b['suggest']}`; fix: [[{b['suggest']}|{b['target']}]]" if b["suggest"] else "")
        F["broken-link"].append({"severity": "warning", "page": b["page"], "detail": detail,
                                 "known": b["known"], "suggest": b["suggest"], "target": b["target"]})

    # hot.md size.
    for p, info in pages.items():
        if p.endswith("wiki/hot.md"):
            n = W.word_count(info["body"])
            if n > HOT_LIMIT:
                F["hot-size"].append({"severity": "warning", "page": p, "detail": f"{n} words (limit {HOT_LIMIT})"})

    # Shared pages: used_in vs '## In <Domain>' sections.
    for p, info in pages.items():
        if info["wiki"] == "shared" and info["fm"]:
            used = set(info["fm"].get("used_in") or [])
            sections = set(re.findall(r"^## In (.+?)\s*$", info["body"], re.M))
            want = {labels.get(u, u) for u in used}
            if want != sections:
                F["shared-sections"].append({"severity": "warning", "page": p,
                                             "detail": f"used_in → {sorted(want)}; sections → {sorted(sections)}"})

    # Promotion candidates: a domain page linked from another domain's pages.
    for target, sources in inbound.items():
        if target.rsplit("/", 1)[-1][:-3].lower() in W.SYSTEM_NAMES:
            continue
        tw = W.wiki_of(target, domains)
        if tw in labels:
            others = sorted({W.wiki_of(s, domains) for s in sources} - {tw, None, "hub", "shared"})
            if others:
                F["promotion-candidate"].append({"severity": "info", "page": target,
                                                 "detail": f"linked from {', '.join(labels[o] for o in others)}"})

    # Orphans and catalog coverage (domain and hub content pages only).
    catalogs = collections.defaultdict(set)
    for p, info in pages.items():
        if W.is_catalog(p) and not p.endswith(("/hot.md", "/log.md")):
            for target, _h, _e in info["links"]:
                for h in resolver.resolve_from(target, p):
                    catalogs[(W.domain_of(p, domains) or {}).get("folder", "")].add(h)
    for p, info in pages.items():
        name = p.rsplit("/", 1)[-1][:-3].lower()
        if not info["wiki"] or name in W.SYSTEM_NAMES or W.is_catalog(p):
            continue
        if not inbound.get(p):
            F["orphan"].append({"severity": "info", "page": p, "detail": "no inbound links"})
        dom = W.domain_of(p, domains)
        if dom and p not in catalogs[dom["folder"]]:
            F["not-in-catalog"].append({"severity": "info", "page": p, "detail": f"not linked from any {dom['folder']} catalog (index, _index, '… Index' pages)"})

    labels_by_wiki = {d["wiki"]: d["folder"] for d in domains}
    for c, phrase, doms, home in missing_pages(files, pages, domains):
        target = home if home == "wiki/shared/" else f"{labels_by_wiki.get(home, home)}/wiki/"
        F["missing-page"].append({"severity": "info", "page": phrase,
                                  "detail": f"mentioned on {c} pages ({', '.join(doms)}) with no page of its own → candidate for {target}"})

    return F, broken, len(pages)


MP_STOP = set("""a an and are as at be but by for from has have in into is it its of on or that the their this
to was were will with which what when where who why how not no can do does did than then there these those we you they
i our your all any each more most other some such only own same so too very just also about per via vs one two new see
if may must should would could up out over under between after before both every here else like yet""".split())
MP_MIN_PAGES = 8


def _norm(w: str) -> str:
    """Singular form for matching: groups → group, but status/radius/class stay."""
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")) else w


def _grams(text: str) -> dict:
    """2- and 3-word phrases (normalised tuple → surface form) that neither start nor end on a stopword."""
    out = {}
    for sent in re.split(r"[.;:!?\n|()\[\]{}\"“”,`*_>]+", text):
        raw = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", sent)
        ws = [_norm(w.lower()) for w in raw]
        for n in (2, 3):
            for i in range(len(ws) - n + 1):
                g = tuple(ws[i:i + n])
                if g[0] in MP_STOP or g[-1] in MP_STOP or any(len(w) < 3 for w in g):
                    continue
                out.setdefault(g, " ".join(raw[i:i + n]).lower())
    return out


def missing_pages(files, pages, domains) -> list:
    """Concepts many pages talk about that have no page of their own.

    A phrase qualifies when it appears (unlinked) on >= MP_MIN_PAGES wiki pages, at least once in
    bold or Title Case in prose (a page treats it as a concept), is not mostly a heading, does not
    occur in any _templates/ file (structure, not knowledge), and matches no page name, title or
    alias, nor a part of one. Candidates only: the wiki-lint skill decides which are real.
    """
    names = {p.rsplit("/", 1)[-1][:-3].lower() for p, _ in files if p.endswith(".md")}
    template_text = ""
    for p, _ in files:
        if "/_templates/" in "/" + p and p.endswith(".md"):
            template_text += W.read(p) + "\n"
    for info in pages.values():
        fm = info["fm"] or {}
        if isinstance(fm.get("title"), str):
            names.add(fm["title"].lower())
        names |= {a.lower() for a in (fm.get("aliases") or []) if isinstance(a, str)}
    name_words = [tuple(_norm(w) for w in re.findall(r"[a-z0-9][a-z0-9\-]*", n)) for n in names]
    templ = set(_grams(template_text))

    count, where, surface, heads, marked = collections.Counter(), collections.defaultdict(set), {}, collections.Counter(), set()
    for p, info in pages.items():
        if not info["wiki"] or p.rsplit("/", 1)[-1][:-3].lower() in W.SYSTEM_NAMES or "/meta/" in p:
            continue
        text = re.sub(r"\[\[[^\]]*\]\]", " | ", W.strip_code(info["body"]))   # linked mentions have pages
        headings = "\n".join(re.findall(r"^#{1,6} (.+)$", text, re.M))
        prose = re.sub(r"^#{1,6} .+$", " ", text, flags=re.M)
        for g, form in _grams(text).items():
            count[g] += 1
            where[g].add(info["wiki"])
            surface.setdefault(g, form)
        heads.update(_grams(headings).keys())
        marks = re.findall(r"\*\*([^*\n]{3,60})\*\*", prose) + re.findall(r"\b(?:[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+)\b", prose)
        marked.update(_grams(" | ".join(marks)).keys())

    def part_of_name(g):
        return any(nw[i:i + len(g)] == g for nw in name_words for i in range(len(nw) - len(g) + 1))

    out = []
    for g, c in count.items():
        doms = where[g] - {"hub"}
        real = doms - {"shared"}
        if c < MP_MIN_PAGES or g not in marked or g in templ or heads[g] / c > 0.3:
            continue
        if part_of_name(g) or " ".join(g) in names or (len(doms) < 2 and c < 12):
            continue
        home = "wiki/shared/" if len(real) >= 2 else next(iter(real or doms), "")
        out.append((c, " ".join(g), sorted(doms), home))
    out.sort(key=lambda x: -x[0])
    return out[:15]


def fix_title_links(broken) -> int:
    """Rewrite [[Title]], [[Title|alias]], [[Title#h]] into path links; leave code and log.md alone."""
    by_page = collections.defaultdict(dict)
    for b in broken:
        if b.get("suggest") and not b["page"].endswith("/log.md"):
            by_page[b["page"]][b["target"]] = b["suggest"]
    n = 0
    for page, mapping in by_page.items():
        text = W.read(page)
        for target, path in mapping.items():
            pat = re.compile(r"(!?)\[\[" + re.escape(target) + r"((?:#[^\]|]*)?)(\\?\|[^\]]*)?\]\]")
            def sub(m, path=path, target=target):
                in_table = False
                alias = m.group(3)
                if not alias:
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    in_table = text[line_start:m.start()].lstrip().startswith("|")
                    alias = ("\\|" if in_table else "|") + target
                return f"{m.group(1)}[[{path}{m.group(2) or ''}{alias}]]"
            text, k = pat.subn(sub, text)
            n += k
        (W.ROOT / page).write_text(text, encoding="utf-8")
    return n


def render(F, n_pages, ci) -> str:
    today = datetime.date.today().isoformat()
    sev = collections.Counter(f["severity"] for fs in F.values() for f in fs)
    new_broken = [f for f in F.get("broken-link", []) if not f.get("known")]
    lines = ["---", "type: meta", f'title: "Lint Report {today}"', "wiki: hub", f"created: {today}", f"updated: {today}",
             "tags: [meta, lint]", "status: developing", "---", "", f"# Lint Report {today}", "",
             f"Scanned **{n_pages}** markdown files · **{sev['error']}** errors · **{sev['warning']}** warnings · "
             f"**{sev['info']}** info · **{len(new_broken)}** new broken links (not in baseline)", ""]
    order = ["duplicate-name", "frontmatter", "wiki-value", "unregistered-domain", "broken-link", "hot-size",
             "shared-sections", "promotion-candidate", "missing-page", "orphan", "not-in-catalog"]
    for name in order:
        fs = F.get(name)
        if not fs:
            continue
        lines += [f"## {name} ({len(fs)})", ""]
        if name == "broken-link":
            fs = sorted(fs, key=lambda f: (f.get("known", False), f["page"]))
        for f in fs[:200]:
            detail = f["detail"] if isinstance(f["detail"], str) else ", ".join(f["detail"])
            tag = "" if name != "broken-link" else (" · known" if f.get("known") else " · **new**")
            lines.append(f"- `{f['page']}` — {detail.replace('[[', '`[[').replace(']]', ']]`')}{tag}")
        if len(fs) > 200:
            lines.append(f"- … {len(fs) - 200} more")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--report", metavar="FILE", help="also write the markdown report to FILE")
    ap.add_argument("--ci", action="store_true", help="exit 1 on errors or on broken links not in the baseline")
    ap.add_argument("--update-baseline", action="store_true", help="record current broken links as known")
    ap.add_argument("--fix-title-links", action="store_true",
                    help="rewrite [[Title]] links that name a page title into [[path|Title]] links, then re-check")
    args = ap.parse_args()

    domains, files, resolver, pages = scan()
    F, broken, n = check(domains, files, resolver, pages)

    if args.fix_title_links:
        fixed = fix_title_links(broken)
        print(f"rewrote {fixed} title links")
        domains, files, resolver, pages = scan()
        F, broken, n = check(domains, files, resolver, pages)

    if args.update_baseline:
        data = {"_comment": "Known broken links. CI fails only on broken links not listed here. "
                            "Regenerate with: python3 scripts/wiki-check.py --update-baseline",
                "updated": datetime.date.today().isoformat(),
                "broken_links": sorted(({"page": b["page"], "target": b["target"]} for b in broken),
                                       key=lambda b: (b["page"], b["target"]))}
        BASELINE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"baseline updated: {len(broken)} known broken links → {W.rel(BASELINE)}")
        return 0

    report = render(F, n, args.ci)
    if args.report:
        out = W.ROOT / args.report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report + "\n", encoding="utf-8")
    print(json.dumps(F, indent=1, ensure_ascii=False) if args.json else report)

    errors = sum(1 for fs in F.values() for f in fs if f["severity"] == "error")
    new_broken = sum(1 for f in F.get("broken-link", []) if not f.get("known"))
    if args.ci and (errors or new_broken):
        print(f"\nwiki-check: {errors} errors, {new_broken} new broken links", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
