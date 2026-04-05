#!/usr/bin/env python3
"""Deterministic preprocessing for llmwiki.

Scans input and .llmwiki/ directories, performs entity matching, frontmatter
extraction, and lint checks. Outputs XML to stdout.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

STALE_THRESHOLD_DAYS = 30

DEFAULT_IGNORES = [
    ".git/",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "venv/",
    ".DS_Store",
    "Thumbs.db",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.o",
    "*.a",
    "*.class",
    "*.egg-info/",
    ".terraform/",
]


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def load_entities(path: Path) -> dict:
    """Load entities.json and return {category: {id: {name, aliases}}}."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if data else {}


def build_alias_map(entities: dict) -> dict[str, tuple[str, str]]:
    """Build alias -> (entity_id, category) reverse map."""
    alias_map: dict[str, tuple[str, str]] = {}
    for category, items in entities.items():
        if not items:
            continue
        for entity_id, info in items.items():
            if not info:
                continue
            name = info.get("name", "")
            if name:
                alias_map[name.lower()] = (entity_id, category)
            alias_map[entity_id.lower()] = (entity_id, category)
            for alias in info.get("aliases", []):
                alias_map[str(alias).lower()] = (entity_id, category)
    return alias_map


def compile_entity_patterns(alias_map: dict[str, tuple[str, str]]) -> list[tuple[re.Pattern, str, str]]:
    """Compile regex patterns for entity matching.

    Longest match first, case-insensitive, word boundary.
    """
    sorted_aliases = sorted(alias_map.keys(), key=len, reverse=True)
    patterns = []
    for alias in sorted_aliases:
        entity_id, category = alias_map[alias]
        escaped = re.escape(alias)
        pattern = re.compile(r"(?<!\w)" + escaped + r"(?!\w)", re.IGNORECASE)
        patterns.append((pattern, entity_id, category))
    return patterns


def extract_text_from_file(path: Path) -> str:
    """Extract text content from a file based on its extension."""
    suffix = path.suffix.lower()
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""

    if suffix == ".json":
        return _extract_json_strings(content)
    elif suffix in {".csv", ".tsv"}:
        return _extract_csv_text(content, suffix)
    else:
        # .md, .hcl, .yaml, .yml, .sh -> as-is
        return content


def _extract_json_strings(content: str) -> str:
    """Parse JSON and concatenate all string values."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content

    strings: list[str] = []
    _collect_strings(data, strings)
    return " ".join(strings)


def _collect_strings(obj, acc: list[str]) -> None:
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, acc)
    elif isinstance(obj, list):
        for item in obj:
            _collect_strings(item, acc)


def _extract_csv_text(content: str, suffix: str) -> str:
    delimiter = "\t" if suffix == ".tsv" else ","
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    cells: list[str] = []
    for row in reader:
        cells.extend(row)
    return " ".join(cells)


def match_entities(text: str, patterns: list[tuple[re.Pattern, str, str]]) -> dict[str, str]:
    """Match entities in text. Returns {entity_id: category}."""
    matched: dict[str, str] = {}
    for pattern, entity_id, category in patterns:
        if pattern.search(text):
            matched[entity_id] = category
    return matched


def _parse_frontmatter_text(text: str) -> dict:
    """Parse simple YAML-like frontmatter without pyyaml.

    Handles flat key: value, simple lists (- item), and
    list-of-dicts (- key: value) used in llmwiki page frontmatter.
    """
    result: dict = {}
    current_key: str | None = None
    current_list: list | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # List item
        if stripped.startswith("- "):
            item_text = stripped[2:].strip()
            if ":" in item_text:
                # - key: value  (part of list-of-dicts)
                k, v = item_text.split(":", 1)
                dict_item = {k.strip(): v.strip()}
                # Peek: if current_list last item is a dict, might need merging
                # For our schema, each "- key: value" under sources is a separate dict field
                # Accumulate into one dict until next "- " at same level
                if current_list is not None and current_list and isinstance(current_list[-1], dict) and indent > 2:
                    current_list[-1][k.strip()] = v.strip()
                else:
                    if current_list is not None:
                        current_list.append(dict_item)
            else:
                if current_list is not None:
                    current_list.append(item_text)
            continue

        # Continuation of list-of-dicts (indented key: value without "- ")
        if indent >= 4 and current_list is not None and ":" in stripped:
            k, v = stripped.split(":", 1)
            if current_list and isinstance(current_list[-1], dict):
                current_list[-1][k.strip()] = v.strip()
            continue

        # Top-level key: value
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v:
                result[k] = v
                current_key = None
                current_list = None
            else:
                # Start of a list or nested block
                current_key = k
                current_list = []
                result[k] = current_list

    return result


def parse_frontmatter(path: Path) -> dict | None:
    """Parse YAML frontmatter from a markdown file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None

    if not content.startswith("---"):
        return None

    end = content.find("---", 3)
    if end == -1:
        return None

    try:
        return _parse_frontmatter_text(content[3:end])
    except Exception:
        return None


def extract_wikilinks(path: Path) -> list[str]:
    """Extract [[entity-id]] wikilinks from a markdown file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def _is_binary(path: Path) -> bool:
    """Detect binary file by checking for null bytes in the first 8192 bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def _parse_gitignore(gitignore_path: Path) -> list[tuple[str, bool, bool]]:
    """Parse a .gitignore file.

    Returns list of (pattern, is_negation, is_dir_only).
    """
    patterns: list[tuple[str, bool, bool]] = []
    try:
        content = gitignore_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return patterns

    for line in content.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue

        is_negation = line.startswith("!")
        if is_negation:
            line = line[1:]

        is_dir_only = line.endswith("/")
        if is_dir_only:
            line = line.rstrip("/")

        if not line:
            continue

        patterns.append((line, is_negation, is_dir_only))

    return patterns


def _matches_gitignore_pattern(
    rel_path: str, is_dir: bool, pattern: str, is_dir_only: bool,
) -> bool:
    """Check if a relative path matches a single gitignore pattern."""
    if is_dir_only and not is_dir:
        return False

    parts = rel_path.split("/")
    basename = parts[-1]

    # Handle **/prefix patterns (match at any directory level)
    if pattern.startswith("**/"):
        rest = pattern[3:]
        if fnmatch.fnmatch(rel_path, rest):
            return True
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            if fnmatch.fnmatch(suffix, rest):
                return True
        return False

    # Handle suffix/** patterns (everything inside directory)
    if pattern.endswith("/**"):
        dir_pattern = pattern[:-3]
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            if fnmatch.fnmatch(prefix, dir_pattern):
                return True
        return False

    # No slash in pattern -> match against basename at any level
    if "/" not in pattern:
        return fnmatch.fnmatch(basename, pattern)

    # Leading slash means anchored to root of gitignore scope
    if pattern.startswith("/"):
        pattern = pattern[1:]

    # Pattern with slash -> match against full relative path
    return fnmatch.fnmatch(rel_path, pattern)


def _default_ignore_rules() -> list[tuple[str, bool, bool, str]]:
    """Build default ignore rules (always applied)."""
    rules: list[tuple[str, bool, bool, str]] = []
    for pattern in DEFAULT_IGNORES:
        is_dir_only = pattern.endswith("/")
        clean = pattern.rstrip("/")
        rules.append((clean, False, is_dir_only, ""))
    return rules


def _is_ignored(
    rel_path: str, is_dir: bool, rules: list[tuple[str, bool, bool, str]],
) -> bool:
    """Check if a path should be ignored based on accumulated rules.

    Rules are applied in order; later rules override earlier ones.
    """
    ignored = False
    for pattern, is_negation, is_dir_only, base_dir in rules:
        if base_dir:
            if not rel_path.startswith(base_dir + "/"):
                continue
            check_path = rel_path[len(base_dir) + 1:]
        else:
            check_path = rel_path

        if _matches_gitignore_pattern(check_path, is_dir, pattern, is_dir_only):
            ignored = not is_negation

    return ignored


def _list_files_git(input_dir: Path) -> list[Path] | None:
    """List files via git ls-files. Returns None if unavailable."""
    if not (input_dir / ".git").exists():
        return None
    if not shutil.which("git"):
        return None
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=input_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        files: list[Path] = []
        for name in result.stdout.split("\0"):
            if not name:
                continue
            path = input_dir / name
            if path.is_file() and path.name != "index.xml" and not _is_binary(path):
                files.append(path)
        return sorted(files)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _walk_with_gitignore(
    input_dir: Path, default_rules: list[tuple[str, bool, bool, str]],
) -> list[Path]:
    """Walk directory tree respecting .gitignore files at each level."""
    files: list[Path] = []

    def _walk(dir_path: Path, inherited_rules: list[tuple[str, bool, bool, str]]) -> None:
        rules = list(inherited_rules)

        gitignore = dir_path / ".gitignore"
        if gitignore.is_file():
            dir_rel = dir_path.relative_to(input_dir)
            base = "" if dir_rel == Path(".") else str(dir_rel)
            for pat, neg, dir_only in _parse_gitignore(gitignore):
                rules.append((pat, neg, dir_only, base))

        try:
            entries = sorted(dir_path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            rel = str(entry.relative_to(input_dir))
            is_dir = entry.is_dir()

            if _is_ignored(rel, is_dir, rules):
                continue

            if is_dir:
                _walk(entry, rules)
            elif entry.is_file():
                if entry.name != "index.xml" and not _is_binary(entry):
                    files.append(entry)

    _walk(input_dir, default_rules)
    return sorted(files)


def scan_input_files(input_dir: Path) -> list[Path]:
    """Recursively find all text files under the input directory.

    Respects .gitignore at each directory level. Uses git ls-files when
    the input directory is a git repository; otherwise falls back to
    manual directory walk with gitignore parsing.
    """
    if not input_dir.exists():
        return []

    # Fast path: use git if available and input_dir is a git repo
    git_files = _list_files_git(input_dir)
    if git_files is not None:
        return git_files

    # Fallback: walk with gitignore parsing
    return _walk_with_gitignore(input_dir, _default_ignore_rules())


def scan_wiki_pages(entities_dir: Path) -> dict:
    """Scan .llmwiki/entities/ and extract frontmatter info."""
    pages: dict = {}
    if not entities_dir.exists():
        return pages
    for path in sorted(entities_dir.rglob("*.md")):
        fm = parse_frontmatter(path)
        if not fm:
            continue
        entity_id = fm.get("entity")
        if not entity_id:
            continue
        sources_ingested = []
        sources_hashes: dict[str, str] = {}
        for s in fm.get("sources", []):
            if isinstance(s, dict) and "path" in s:
                sources_ingested.append(s["path"])
                if "sha256" in s:
                    sources_hashes[s["path"]] = s["sha256"]
        related = fm.get("related", []) or []
        wikilinks = extract_wikilinks(path)
        updated = fm.get("updated", "")
        if isinstance(updated, datetime):
            updated = updated.strftime("%Y-%m-%d")
        pages[entity_id] = {
            "path": str(path),
            "sources_ingested": sources_ingested,
            "sources_hashes": sources_hashes,
            "related": related,
            "wikilinks": wikilinks,
            "updated": str(updated),
        }
    return pages


def count_contradictions(entities_dir: Path) -> dict:
    """Count 'needs review' flags in wiki pages."""
    total = 0
    pages: list[str] = []
    if not entities_dir.exists():
        return {"total": 0, "pages": []}
    for path in sorted(entities_dir.rglob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        count = content.count("needs review")
        if count > 0:
            fm = parse_frontmatter(path)
            entity_id = fm.get("entity", path.stem) if fm else path.stem
            pages.append(entity_id)
            total += count
    return {"total": total, "pages": sorted(pages)}


def run_lint(
    wiki_pages: dict,
    entity_coverage: dict,
    raw_files_info: list[dict],
    entities: dict,
    entities_dir: Path | None = None,
) -> dict:
    """Run lint checks."""
    all_entity_ids = set()
    for category, items in entities.items():
        if items:
            all_entity_ids.update(items.keys())

    # Orphan pages: wiki pages with zero incoming links
    all_linked: set[str] = set()
    for page_info in wiki_pages.values():
        all_linked.update(page_info.get("wikilinks", []))
        all_linked.update(page_info.get("related", []))
    orphan_pages = [eid for eid in wiki_pages if eid not in all_linked]

    # Broken links: wikilinks pointing to non-existent entities
    broken_links: list[str] = []
    for page_info in wiki_pages.values():
        for link in page_info.get("wikilinks", []):
            if link not in wiki_pages and link not in all_entity_ids:
                if link not in broken_links:
                    broken_links.append(link)

    # Stale pages: updated more than STALE_THRESHOLD_DAYS ago
    stale_pages: list[str] = []
    cutoff = (datetime.now() - timedelta(days=STALE_THRESHOLD_DAYS)).strftime("%Y-%m-%d")
    for eid, page_info in wiki_pages.items():
        updated = page_info.get("updated", "")
        if updated and updated < cutoff:
            stale_pages.append(eid)

    # Uncovered files: entity match exists but not yet ingested
    all_ingested: set[str] = set()
    for page_info in wiki_pages.values():
        all_ingested.update(page_info.get("sources_ingested", []))
    uncovered_files: list[str] = []
    for file_info in raw_files_info:
        if file_info["known_entities"] and file_info["path"] not in all_ingested:
            uncovered_files.append(file_info["path"])

    # Contradictions: count "needs review" flags
    contradictions = count_contradictions(entities_dir) if entities_dir else {"total": 0, "pages": []}

    return {
        "orphan_pages": sorted(orphan_pages),
        "broken_links": sorted(broken_links),
        "stale_pages": sorted(stale_pages),
        "uncovered_files": sorted(uncovered_files),
        "contradictions": contradictions,
    }


def preprocess(input_dir: Path, wiki_dir: Path) -> dict:
    """Run full preprocessing pipeline."""
    entities_file = wiki_dir / "entities.json"
    entities_dir = wiki_dir / "entities"

    entities = load_entities(entities_file)
    alias_map = build_alias_map(entities)
    patterns = compile_entity_patterns(alias_map)

    # Scan input files
    raw_files = scan_input_files(input_dir)

    # Scan wiki pages
    wiki_pages = scan_wiki_pages(entities_dir)

    # Build maps of already-ingested source paths and their hashes
    all_ingested: set[str] = set()
    ingested_hashes: dict[str, str] = {}  # path -> sha256
    for page_info in wiki_pages.values():
        all_ingested.update(page_info.get("sources_ingested", []))
        for src_path, src_hash in page_info.get("sources_hashes", {}).items():
            ingested_hashes[src_path] = src_hash

    # Process each raw file
    raw_files_info: list[dict] = []
    entity_coverage: dict[str, dict] = {}
    new_files: list[dict] = []
    updated_files: list[dict] = []
    current_paths: set[str] = set()

    for path in raw_files:
        rel_path = str(path)
        current_paths.add(rel_path)
        sha256 = compute_sha256(path)
        text = extract_text_from_file(path)
        matched = match_entities(text, patterns)

        file_info = {
            "path": rel_path,
            "file_type": path.suffix.lstrip(".").lower(),
            "sha256": sha256,
            "known_entities": matched,
        }
        raw_files_info.append(file_info)

        # Track entity coverage
        for eid, cat in matched.items():
            if eid not in entity_coverage:
                entity_coverage[eid] = {"mentions": 0, "has_wiki_page": eid in wiki_pages}
            entity_coverage[eid]["mentions"] += 1

        if rel_path not in all_ingested:
            # New file = not yet ingested
            new_files.append(file_info)
        elif rel_path in ingested_hashes and ingested_hashes[rel_path] != sha256:
            # Updated file = ingested but content changed
            file_info["previous_sha256"] = ingested_hashes[rel_path]
            updated_files.append(file_info)

    # Missing sources = ingested paths that no longer exist on disk
    missing_sources: list[dict] = []
    for ingested_path in sorted(all_ingested):
        if ingested_path not in current_paths:
            # Find which entities referenced this source
            affected_entities = []
            for eid, page_info in wiki_pages.items():
                if ingested_path in page_info.get("sources_ingested", []):
                    affected_entities.append(eid)
            missing_sources.append({
                "path": ingested_path,
                "affected_entities": affected_entities,
            })

    # Count entities in dict
    entities_in_dict = sum(len(items) for items in entities.values() if items)

    # Lint
    lint = run_lint(wiki_pages, entity_coverage, raw_files_info, entities, entities_dir)

    return {
        "stats": {
            "total_files": len(raw_files),
            "new_files": len(new_files),
            "updated_files": len(updated_files),
            "missing_sources": len(missing_sources),
            "wiki_pages": len(wiki_pages),
            "entities_in_dict": entities_in_dict,
        },
        "new_files": new_files,
        "updated_files": updated_files,
        "missing_sources": missing_sources,
        "entity_coverage": entity_coverage,
        "wiki_pages": wiki_pages,
        "lint": lint,
    }


def result_to_xml(result: dict) -> str:
    """Convert preprocessing result dict to XML string."""
    root = ET.Element("llmwiki-preprocess")

    # stats
    stats = result["stats"]
    ET.SubElement(root, "stats", attrib={
        k.replace("_", "-"): str(v) for k, v in stats.items()
    })

    # new-files
    new_files_el = ET.SubElement(root, "new-files")
    for f in result["new_files"]:
        file_el = ET.SubElement(new_files_el, "file",
                                path=f["path"], type=f["file_type"], sha256=f["sha256"])
        for eid, cat in f["known_entities"].items():
            ET.SubElement(file_el, "entity", id=eid, category=cat)

    # updated-files
    updated_files_el = ET.SubElement(root, "updated-files")
    for f in result["updated_files"]:
        attribs = {"path": f["path"], "type": f["file_type"], "sha256": f["sha256"]}
        if "previous_sha256" in f:
            attribs["previous-sha256"] = f["previous_sha256"]
        file_el = ET.SubElement(updated_files_el, "file", attrib=attribs)
        for eid, cat in f["known_entities"].items():
            ET.SubElement(file_el, "entity", id=eid, category=cat)

    # missing-sources
    missing_el = ET.SubElement(root, "missing-sources")
    for ms in result["missing_sources"]:
        src_el = ET.SubElement(missing_el, "source", path=ms["path"])
        for eid in ms["affected_entities"]:
            ET.SubElement(src_el, "affected-entity", id=eid)

    # entity-coverage
    cov_el = ET.SubElement(root, "entity-coverage")
    for eid, info in result["entity_coverage"].items():
        ET.SubElement(cov_el, "entity", attrib={
            "id": eid,
            "mentions": str(info["mentions"]),
            "has-wiki-page": str(info["has_wiki_page"]).lower(),
        })

    # wiki-pages
    pages_el = ET.SubElement(root, "wiki-pages")
    for eid, info in result["wiki_pages"].items():
        page_el = ET.SubElement(pages_el, "page", attrib={
            "entity-id": eid, "path": info["path"], "updated": info["updated"],
        })
        for src_path in info["sources_ingested"]:
            sha = info["sources_hashes"].get(src_path, "")
            attribs = {"path": src_path}
            if sha:
                attribs["sha256"] = sha
            ET.SubElement(page_el, "source", attrib=attribs)
        for rel in info["related"]:
            ET.SubElement(page_el, "related", attrib={"entity-id": rel})
        for wl in info["wikilinks"]:
            ET.SubElement(page_el, "wikilink", attrib={"entity-id": wl})

    # lint
    lint = result["lint"]
    lint_el = ET.SubElement(root, "lint")

    orphan_el = ET.SubElement(lint_el, "orphan-pages")
    for eid in lint["orphan_pages"]:
        ET.SubElement(orphan_el, "entity", id=eid)

    broken_el = ET.SubElement(lint_el, "broken-links")
    for link in lint["broken_links"]:
        ET.SubElement(broken_el, "link", target=link)

    stale_el = ET.SubElement(lint_el, "stale-pages")
    for eid in lint["stale_pages"]:
        ET.SubElement(stale_el, "entity", id=eid)

    uncov_el = ET.SubElement(lint_el, "uncovered-files")
    for path in lint["uncovered_files"]:
        ET.SubElement(uncov_el, "file", path=path)

    contradictions = lint["contradictions"]
    contr_el = ET.SubElement(lint_el, "contradictions", total=str(contradictions["total"]))
    for eid in contradictions["pages"]:
        ET.SubElement(contr_el, "entity", id=eid)

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def ensure_llmwiki_dir(wiki_dir: Path) -> None:
    """Create .llmwiki/ structure if it doesn't exist."""
    wiki_dir.mkdir(exist_ok=True)
    entities_file = wiki_dir / "entities.json"
    if not entities_file.exists():
        entities_file.write_text(
            json.dumps({"services": {}, "environments": {}, "components": {}, "procedures": {}, "concepts": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
    for category in ("services", "environments", "components", "procedures", "concepts"):
        (wiki_dir / "entities" / category).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Deterministic preprocessing for llmwiki")
    parser.add_argument("input_dir", type=Path, help="Directory to scan recursively")
    parser.add_argument("--llmwiki-dir", type=Path, default=None,
                        help="llmwiki output directory (default: .llmwiki)")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    wiki_dir = args.llmwiki_dir.resolve() if args.llmwiki_dir else Path.cwd() / ".llmwiki"
    ensure_llmwiki_dir(wiki_dir)

    result = preprocess(input_dir, wiki_dir)
    sys.stdout.write(result_to_xml(result))


if __name__ == "__main__":
    main()
