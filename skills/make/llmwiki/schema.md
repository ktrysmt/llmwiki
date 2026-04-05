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
- Fact [source-id or [[entity-id]]]
- If contradictions exist, include both values with dates and add a "needs review" flag

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
3. Append to Key Facts. If contradictory values exist, include both with dates and add a "needs review" flag
4. Add Relations bidirectionally (if adding A->B, also add B->A)
5. Add new sources to the Source Files table
6. Append changes to Changelog

## Source Type

Trust order: primary > secondary > derived

The `source_type` of a source is determined by the LLM reading both the file path and content during llmwiki:make Phase 1. Provenance information is delegated to `sources[].path`.

Determination guidelines:
- primary: Official configuration files, IaC definitions, official documentation, API responses, etc. Authoritative and highly accurate descriptions
- secondary: Meeting notes, chat logs, unofficial documentation, personal notes, etc. Information is useful but may require verification
- derived: Secondary documents synthesized by llmwiki:query or llmwiki:docs. Integrations of information from source entities

During contradiction resolution (llmwiki:metabolize), values from higher-trust sources are presented as priority candidates.

## Entity ID Convention

- Lowercase, kebab-case
- Examples: `amazon-ecs`, `production`, `vpc-main`
- Aliases are registered in entities.json in both English and Japanese
