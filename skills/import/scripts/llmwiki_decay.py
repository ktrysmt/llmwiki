#!/usr/bin/env python3
"""Detect llmwiki pages that have not been updated for a long time.

Outputs XML with decay candidates sorted by priority.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def parse_frontmatter(path: Path) -> dict | None:
    """Parse simple YAML-like frontmatter from a markdown file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
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
            result[k.strip()] = v.strip()
    return result


def extract_wikilinks(path: Path) -> list[str]:
    """Extract [[entity-id]] wikilinks from a markdown file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def scan_decay_candidates(wiki_dir: Path, threshold_days: int) -> dict:
    """Find pages not updated within threshold_days."""
    entities_dir = wiki_dir / "entities"
    today = datetime.now()

    # First pass: collect all pages and their wikilinks/related
    all_pages: dict[str, dict] = {}
    all_outgoing: dict[str, list[str]] = {}

    if not entities_dir.exists():
        return {"candidates": [], "summary": {"total_pages": 0, "decay_candidates": 0, "threshold_days": threshold_days}}

    for path in sorted(entities_dir.rglob("*.md")):
        fm = parse_frontmatter(path)
        if not fm:
            continue
        entity_id = fm.get("entity", "")
        if not entity_id:
            continue

        updated_str = fm.get("updated", "")
        category = fm.get("category", "")

        # Parse updated date
        days_since = 0
        if updated_str:
            try:
                updated_date = datetime.strptime(updated_str, "%Y-%m-%d")
                days_since = (today - updated_date).days
            except ValueError:
                days_since = 0

        all_pages[entity_id] = {
            "entity_id": entity_id,
            "category": category,
            "updated": updated_str,
            "days_since_update": days_since,
            "path": str(path),
        }

        # Collect outgoing references (wikilinks + related)
        wikilinks = extract_wikilinks(path)
        related = []
        try:
            content = path.read_text(encoding="utf-8")
            # Extract related from frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    fm_text = content[3:end]
                    in_related = False
                    for line in fm_text.splitlines():
                        stripped = line.strip()
                        if stripped == "related:":
                            in_related = True
                            continue
                        if in_related and stripped.startswith("- "):
                            related.append(stripped[2:].strip())
                        elif in_related and not stripped.startswith("-") and ":" in stripped:
                            in_related = False
        except (UnicodeDecodeError, OSError):
            pass

        all_outgoing[entity_id] = list(set(wikilinks + related))

    # Count incoming references for each page
    incoming_count: dict[str, int] = {eid: 0 for eid in all_pages}
    for source_id, targets in all_outgoing.items():
        for target in targets:
            if target in incoming_count:
                incoming_count[target] += 1

    # Build candidates list (only pages with zero incoming references)
    candidates = []
    for entity_id, info in all_pages.items():
        if info["days_since_update"] >= threshold_days and incoming_count.get(entity_id, 0) == 0:
            candidates.append({
                "entity_id": entity_id,
                "category": info["category"],
                "updated": info["updated"],
                "days_since_update": info["days_since_update"],
                "incoming_references": 0,
            })

    # Sort: days_since_update descending (oldest first)
    candidates.sort(key=lambda c: -c["days_since_update"])

    return {
        "candidates": candidates,
        "summary": {
            "total_pages": len(all_pages),
            "decay_candidates": len(candidates),
            "threshold_days": threshold_days,
        },
    }


def result_to_xml(result: dict) -> str:
    """Convert decay result dict to XML string."""
    summary = result["summary"]
    root = ET.Element("llmwiki-decay", attrib={
        "total-pages": str(summary["total_pages"]),
        "decay-candidates": str(summary["decay_candidates"]),
        "threshold-days": str(summary["threshold_days"]),
    })

    for c in result["candidates"]:
        ET.SubElement(root, "candidate", attrib={
            "entity-id": c["entity_id"],
            "category": c["category"],
            "updated": c["updated"],
            "days-since-update": str(c["days_since_update"]),
            "incoming-references": str(c["incoming_references"]),
        })

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def main():
    parser = argparse.ArgumentParser(description="Detect stale llmwiki pages for decay")
    parser.add_argument("--llmwiki-dir", type=Path, required=True,
                        help="llmwiki directory (e.g. .llmwiki)")
    parser.add_argument("--threshold-days", type=int, default=90,
                        help="Days since last update to consider for decay (default: 90)")
    args = parser.parse_args()

    wiki_dir = args.llmwiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: {wiki_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    result = scan_decay_candidates(wiki_dir, args.threshold_days)
    sys.stdout.write(result_to_xml(result))


if __name__ == "__main__":
    main()
