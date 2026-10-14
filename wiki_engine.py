#!/usr/bin/env python3
"""Install the reusable wiki engine into a project without copying wiki content."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ENGINE = Path(__file__).resolve().parent / "engine"
MANIFEST = Path('.vault-meta/engine-manifest.json')
TOOLS = [
    *sorted(p for p in (ENGINE / 'scripts').glob('*') if p.is_file()),
    *sorted((ENGINE / '.claude/skills').glob('*/SKILL.md')),
    ENGINE / '.claude/agents/wiki-ingest-worker.md',
    ENGINE / '.claude/NOTICE.md',
    ENGINE / '.github/workflows/wiki-check.yml',
    ENGINE / 'WIKI.md',
    ENGINE / '.claude/settings.json',
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def install(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    manifest_file = target / MANIFEST
    old = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    new = dict(old)
    conflicts = []
    for src in TOOLS:
        rel = src.relative_to(ENGINE).as_posix()
        dst = target / rel
        content = src.read_bytes()
        if dst.exists() and dst.read_bytes() != content:
            if old.get(rel) != digest(dst.read_bytes()):
                conflicts.append(rel)
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
        if src.suffix == '.sh' or src.suffix == '.py':
            dst.chmod(dst.stat().st_mode | 0o111)
        new[rel] = digest(content)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(new, indent=2, sort_keys=True) + '\n')
    if conflicts:
        print('Kept locally edited files: ' + ', '.join(conflicts), file=sys.stderr)
        print('Review these files before updating them manually.', file=sys.stderr)
    print(f'Installed engine in {target}')


def page(kind: str, wiki: str, title: str, body: str) -> str:
    today = date.today().isoformat()
    return f'---\ntype: {kind}\ntitle: "{title}"\nwiki: {wiki}\nstatus: seed\ncreated: {today}\nupdated: {today}\n---\n\n# {title}\n\n{body}\n'


def init(target: Path, domain: str, scope: str) -> None:
    if any(target.iterdir()) if target.exists() else False:
        sys.exit(f'{target} is not empty; use install for an existing wiki')
    slug = re.sub(r'[^a-z0-9]+', '-', domain.lower()).strip('-')
    if not slug:
        sys.exit('domain must contain letters or numbers')
    install(target)
    registry = {'domains': [{'folder': domain, 'wiki': slug, 'label': domain, 'prefix': domain + ' — ', 'scope': scope}]}
    (target / '.vault-meta/domains.json').write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n')
    (target / '.vault-meta/lint-baseline.json').write_text('{"broken_links": []}\n')
    hub = target / 'wiki'
    (hub / 'shared').mkdir(parents=True)
    (hub / 'cross-domain').mkdir()
    (hub / 'index.md').write_text(page('index', 'hub', 'Wiki Index', f'## Domains\n\n- {domain} — {scope}; see `{domain}/wiki/index.md`.\n\n## Shared pages\n\n## Cross-domain questions'))
    (hub / 'hot.md').write_text(page('meta', 'hub', 'Recent Context', '## Last Updated\n\nNo updates yet.\n\n## Key Recent Facts\n\n## Recent Changes\n\n## Active Threads'))
    (hub / 'log.md').write_text(page('meta', 'hub', 'Wiki Log', ''))
    d = target / domain
    for folder in ['.raw/articles', '.raw/transcripts', '.raw/data', '.raw/assets', '_attachments', 'deliverables', '_templates', 'wiki/sources', 'wiki/entities', 'wiki/concepts', 'wiki/comparisons', 'wiki/questions', 'wiki/decisions', 'wiki/meta']:
        path = d / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / '.gitkeep').touch()
    w = d / 'wiki'
    (w / 'index.md').write_text(page('index', slug, domain + ' Index', '## Sources\n\n## Entities\n\n## Concepts\n\n## Comparisons\n\n## Questions\n\n## Decisions'))
    (w / 'hot.md').write_text(page('meta', slug, 'Recent Context', '## Last Updated\n\nNo updates yet.\n\n## Key Recent Facts\n\n## Recent Changes\n\n## Active Threads'))
    (w / 'log.md').write_text(page('meta', slug, 'Wiki Log', ''))
    (w / 'overview.md').write_text(page('overview', slug, domain + ' Overview', scope))
    for template in (ENGINE / 'templates').glob('*.md'):
        (d / '_templates' / template.name).write_text(template.read_text().replace('{{wiki}}', slug))
    (target / 'CLAUDE.md').write_text(f'# Wiki\n\nThis repository is a wiki for {domain}. Page format: `WIKI.md`.\n\n## Domains\n\n| Domain | Owns | Start at |\n|---|---|---|\n| `{domain}/` | {scope} | `{domain}/wiki/hot.md` |\n\nThe machine-readable registry is `.vault-meta/domains.json`.\n\n## Routing\n\nRead `wiki/hot.md` and `wiki/index.md`, then the domain hot cache and index. Use `scripts/wiki-search.py` and `scripts/wiki-graph.py` to find and expand pages. Store raw sources in `<Domain>/.raw/`, knowledge in `<Domain>/wiki/`, and final documents in `<Domain>/deliverables/`. Promote a page to `wiki/shared/` when two domains need it.\n\nUse the installed Claude wiki skills for ingest, query, save, lint, search, and new domains.\n')
    (target / '.gitignore').write_text('.DS_Store\n__pycache__/\n.vault-meta/search/\n.vault-meta/.touched-wikis\n.claude/settings.local.json\n**/.env\n**/.envrc\n')
    print(f'Created wiki for {domain} at {target}')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    a = sub.add_parser('init', help='create a new, empty wiki')
    a.add_argument('target', type=Path)
    a.add_argument('--domain', required=True, help='first domain folder name')
    a.add_argument('--scope', required=True, help='what this domain covers')
    b = sub.add_parser('install', help='install or update engine files in an existing wiki')
    b.add_argument('target', type=Path)
    args = ap.parse_args()
    if args.command == 'init':
        init(args.target.resolve(), args.domain, args.scope)
    else:
        install(args.target.resolve())


if __name__ == '__main__':
    main()
