#!/usr/bin/env python3
"""
remove_wikipedia_references.py

One-off cleanup: strip the Wikipedia "sameAs" entity references that the old SEO
enrichment step (scripts/process_seo_enrichment.js) folded into Article.about[].

We no longer want these. This walks every content JSON and deletes any "sameAs"
key whose value is a Wikipedia URL or a leftover null placeholder, anywhere in the
tree. The entity objects themselves (@type / name / description) are kept -- only
the wiki link is removed.

Formatting is preserved to keep the diff minimal: 2-space indent (matching the
original JSON.stringify output), raw (non-escaped) unicode, and each file's own
newline style + trailing-newline presence.

Usage:
    python scripts/remove_wikipedia_references.py            # clean content-source/
    python scripts/remove_wikipedia_references.py <dir>      # clean a specific dir
    python scripts/remove_wikipedia_references.py --dry-run  # report, write nothing
"""

import argparse
import json
import sys
from pathlib import Path


def should_drop(value):
    """True if a sameAs value is a wiki reference or a null placeholder."""
    if value is None:
        return True
    if isinstance(value, str) and "wikipedia" in value.lower():
        return True
    return False


def strip_same_as(node):
    """Recursively delete wiki/null 'sameAs' keys. Returns count removed."""
    removed = 0
    if isinstance(node, dict):
        if "sameAs" in node and should_drop(node["sameAs"]):
            del node["sameAs"]
            removed += 1
        for value in node.values():
            removed += strip_same_as(value)
    elif isinstance(node, list):
        for item in node:
            removed += strip_same_as(item)
    return removed


def process_file(path, dry_run):
    """Returns count of sameAs removed from this file (0 if unchanged)."""
    # newline="" disables universal-newline translation so we can detect and
    # preserve the file's real line-ending style (these files are CRLF).
    with path.open("r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    data = json.loads(raw)

    removed = strip_same_as(data)
    if removed == 0:
        return 0

    if not dry_run:
        newline = "\r\n" if "\r\n" in raw else "\n"
        out = json.dumps(data, ensure_ascii=False, indent=2)
        out = out.replace("\n", newline)
        if raw.endswith(("\n", "\r")):
            out += newline
        path.write_text(out, encoding="utf-8", newline="")

    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=None,
        help="Directory to scan (default: <repo>/content-source)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing files",
    )
    args = parser.parse_args()

    if args.root:
        root = Path(args.root)
    else:
        root = Path(__file__).resolve().parent.parent / "content-source"

    if not root.exists():
        sys.exit(f"Error: directory not found: {root}")

    files = sorted(root.rglob("*.json"))
    changed_files = 0
    total_removed = 0

    for path in files:
        try:
            removed = process_file(path, args.dry_run)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  SKIP {path}: {exc}", file=sys.stderr)
            continue
        if removed:
            changed_files += 1
            total_removed += removed
            print(f"  {path.relative_to(root)}: removed {removed}")

    verb = "would remove" if args.dry_run else "removed"
    print(
        f"\nScanned {len(files)} JSON file(s) under {root}. "
        f"{verb} {total_removed} wiki reference(s) across {changed_files} file(s)."
    )


if __name__ == "__main__":
    main()
