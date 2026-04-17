#!/usr/bin/env python3
"""Generate .llmwiki/index.xml as a content catalog.

Scans .llmwiki/entities/ for wiki pages, extracts frontmatter and
Overview first sentence, and outputs a categorized XML index.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

CATEGORIES = ("services", "environments", "components", "procedures", "concepts")


def parse_frontmatter(content: str) -> dict | None:
    """Parse simple YAML-like frontmatter from markdown content."""
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    result: dict = {}
    for line in content[3:end].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v:
                result[k] = v
    return result


def extract_overview_first_sentence(content: str) -> str:
    """Extract the first non-empty line after ## Overview."""
    in_overview = False
    for line in content.splitlines():
        if re.match(r"^##\s+Overview", line):
            in_overview = True
            continue
        if in_overview:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            return stripped
    return ""


def generate_index(wiki_dir: Path) -> str:
    """Generate index.xml content from llmwiki entities."""
    entities_dir = wiki_dir / "entities"

    # Collect pages by category
    by_category: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}

    if entities_dir.exists():
        for path in sorted(entities_dir.rglob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            fm = parse_frontmatter(content)
            if not fm:
                continue

            entity_id = fm.get("entity", "")
            category = fm.get("category", "")
            updated = fm.get("updated", "")

            if not entity_id or not category:
                continue

            overview = extract_overview_first_sentence(content)
            entry = {
                "entity_id": entity_id,
                "overview": overview,
                "updated": updated,
            }

            if category in by_category:
                by_category[category].append(entry)
            else:
                by_category[category] = [entry]

    # Count total
    total = sum(len(entries) for entries in by_category.values())

    # Build XML tree
    root = ET.Element("llmwiki-index", attrib={
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": str(total),
    })

    for category in CATEGORIES:
        entries = by_category.get(category, [])
        if not entries:
            continue
        cat_el = ET.SubElement(root, "category", name=category)
        for entry in entries:
            entity_el = ET.SubElement(cat_el, "entity",
                                      id=entry["entity_id"], updated=entry["updated"])
            entity_el.text = entry["overview"]

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate llmwiki index.xml catalog")
    parser.add_argument("--llmwiki-dir", type=Path, required=True,
                        help="llmwiki directory (e.g. .llmwiki)")
    args = parser.parse_args()

    wiki_dir = args.llmwiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    content = generate_index(wiki_dir)
    index_file = wiki_dir / "index.xml"
    index_file.write_text(content, encoding="utf-8")
    print(f"Index written to {index_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
