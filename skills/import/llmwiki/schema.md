# llmwiki Page Schema

Wiki pages follow the template below.

## Template

```markdown
---
entity: <entity-id>
category: <services|environments|components|procedures|concepts>
sources:
  - path: <absolute path to source file>
    source_type: <primary|secondary|derived>
    sha256: <SHA-256 hash of source file>
    ingested: <YYYY-MM-DD>
related:
  - <entity-id>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <Entity Name>

## Overview
(Self-contained description of the entity)

## Key Facts
- Fact [source: filename.json, primary, 2026-04-01]
- Fact without provenance (legacy or unresolvable)
- Value A [source: config.json, primary, 2026-04-01] vs Value B [source: notes.md, secondary, 2026-03-15] -- needs review

## Relations
- [[related-entity-id]] -- Description of relationship

## Source Files
| Date | File | Type |
|---|---|---|
| YYYY-MM-DD | filename | primary/secondary/derived |

## Changelog
- YYYY-MM-DD: Description of changes
```

## Merge Rules

When updating an existing page:
1. Add new sources to frontmatter `sources`. Update `updated` to today
2. Preserve existing Overview descriptions while supplementing/correcting with new information
3. Append to Key Facts with fact-level provenance: `- Fact [source: filename, source_type, YYYY-MM-DD]`. If contradictory values exist, include both with provenance and add a "needs review" flag: `- Value A [source: file-a, primary, 2026-04-01] vs Value B [source: file-b, secondary, 2026-03-15] -- needs review`. Existing facts without provenance (legacy) are left as-is until the next fix or re-ingestion
4. Add Relations bidirectionally (if adding A->B, also add B->A)
5. Add new sources to the Source Files table
6. Append changes to Changelog

## Source Type

Trust order: primary > secondary > derived

The `source_type` of a source is determined by the LLM reading both the file path and content during llmwiki:update Phase 1. Provenance information is delegated to `sources[].path`.

Determination guidelines:
- primary: Official configuration files, IaC definitions, official documentation, API responses, etc. Authoritative and highly accurate descriptions
- secondary: Meeting notes, chat logs, unofficial documentation, personal notes, etc. Information is useful but may require verification
- derived: Secondary documents synthesized by llmwiki:query or llmwiki:docs. Integrations of information from source entities

During contradiction resolution (llmwiki:update Phase 3), values from higher-trust sources are presented as priority candidates.

## Fact-Level Provenance

Each Key Fact should include an inline provenance tag indicating which source file contributed the fact:

```
- Fact description [source: filename, source_type, YYYY-MM-DD]
```

- `filename`: Base name of the source file (not full path, for readability)
- `source_type`: primary / secondary / derived
- `YYYY-MM-DD`: The date the fact was ingested from this source

Facts without provenance tags are treated as legacy data. They are valid but cannot participate in automated trust-based contradiction resolution. Provenance is backfilled during:
- `/llmwiki:update` Phase 1: New and updated facts receive provenance at ingestion time
- `/llmwiki:update` Phase 3 (auto-fix): When resolving contradictions, all facts on the page are checked and missing provenance is backfilled where the source can be determined from the page's `sources[]` frontmatter

## Entity ID Convention

- Lowercase, kebab-case
- Examples: `amazon-ecs`, `production`, `vpc-main`
- Aliases are registered in entities.json in both English and Japanese
