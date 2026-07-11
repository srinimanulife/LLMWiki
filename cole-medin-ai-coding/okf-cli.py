#!/usr/bin/env python3
"""okf-cli.py - a tiny, dependency-free CLI to navigate and search this OKF bundle.

This repo is an Open Knowledge Format (OKF) bundle: just markdown files with YAML
frontmatter, navigated via index.md. You can read the files directly; this CLI
just makes search and navigation one command. Standard library only; no installs.

Run it from anywhere (it always operates on the folder it lives in):

    python okf-cli.py index [subpath]     # print an index.md (start at the root)
    python okf-cli.py read <path>         # print a page (e.g. concepts/the-piv-loop)
    python okf-cli.py find "<query>"      # ranked keyword search across the bundle
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESERVED = {"index.md", "log.md", "README.md"}


def _safe(rel: str) -> Path | None:
    """Resolve rel under ROOT, refusing anything that escapes the bundle."""
    p = (ROOT / rel).resolve()
    return p if p == ROOT or ROOT in p.parents else None


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_text, body). Tolerates a missing block."""
    if text.startswith("---"):
        lines = text.splitlines()
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]).lstrip("\n")
    return "", text


def _field(frontmatter: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", frontmatter, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def cmd_index(args: list[str]) -> int:
    sub = args[0] if args else ""
    target = _safe(sub) if sub else ROOT
    if target is None or not target.is_dir():
        print(f"✗ no such directory in bundle: {sub}")
        return 1
    idx = target / "index.md"
    if idx.exists():
        print(idx.read_text(encoding="utf-8"))
        return 0
    print(f"(no index.md in {sub or '<root>'}; synthesizing a listing)\n")
    for c in sorted(target.iterdir()):
        if c.is_dir():
            print(f"* {c.name}/")
        elif c.suffix == ".md" and c.name not in RESERVED:
            print(f"* {c.relative_to(ROOT).as_posix()[:-3]}")
    return 0


def cmd_read(args: list[str]) -> int:
    if not args:
        print("usage: python okf-cli.py read <path>   (e.g. concepts/the-piv-loop)")
        return 1
    rel = args[0] if args[0].endswith(".md") else f"{args[0]}.md"
    p = _safe(rel)
    if p is None or not p.exists():
        print(f"✗ not found: {args[0]}")
        return 1
    print(p.read_text(encoding="utf-8"))
    return 0


def cmd_find(args: list[str]) -> int:
    limit, terms, i = 15, [], 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
            continue
        terms.append(args[i])
        i += 1
    needles = [t.lower() for t in " ".join(terms).split() if t.strip()]
    if not needles:
        print('usage: python okf-cli.py find "<query>"')
        return 1

    hits: list[tuple[int, str, str]] = []
    for md in sorted(ROOT.rglob("*.md")):
        if md.name in RESERVED:
            continue
        fm, body = _split_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        strong, weak = fm.lower(), body.lower()
        score = sum(3 * strong.count(n) + (1 if n in weak else 0) for n in needles)
        if score:
            cid = md.relative_to(ROOT).as_posix()[:-3]
            hits.append((score, cid, _field(fm, "title")))
    if not hits:
        print(f"No matches for '{' '.join(needles)}'.")
        return 0
    hits.sort(key=lambda h: (-h[0], h[1]))
    print(f"Matches for '{' '.join(terms)}':\n")
    for score, cid, title in hits[:limit]:
        print(f"  [{score:>3}] {cid}")
        if title:
            print(f"        {title}")
    return 0


COMMANDS = {"index": cmd_index, "read": cmd_read, "find": cmd_find}


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 1
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
