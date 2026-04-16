---
name: docs
description: Generate structured documents on a specified theme by synthesizing multiple entities from .llmwiki/. Use when the user wants to produce architecture overviews, procedure guides, onboarding materials, or other multi-entity documents.
argument-hint: "<theme or question>"
allowed-tools: Read Edit Write
---

# /llmwiki:docs

Generate structured documents on a specified theme based on knowledge in .llmwiki/.

## Wiki State

```!
if [ -d .llmwiki ]; then
  entity_count=$(find .llmwiki/entities -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  echo "status: initialized"
  echo "entity_pages: ${entity_count}"
  echo "index: $(test -f .llmwiki/index.xml && echo 'exists' || echo 'missing')"
else
  echo "status: not_initialized (run /llmwiki:update first)"
fi
```

If Wiki State shows not_initialized, inform the user and stop.
If index is missing, inform the user to run /llmwiki:update first.

## Arguments

`/llmwiki:docs <theme or question>`

Examples:
- `/llmwiki:docs Production environment architecture overview`
- `/llmwiki:docs ECS service deployment procedure`
- `/llmwiki:docs Onboarding materials`

## Procedure

### Step 1: Scope Determination

1. Read `.llmwiki/index.xml`
2. Identify entities related to the theme
3. Recursively follow Relations to collect related entities (up to 2 hops)
4. Present the list of target entities to the user and confirm the scope

### Step 2: Quality Check

Among the target entities:
- Report pages with "needs review" flags
- Report stale pages (including dormant pages)
- If contradictions exist, recommend running /llmwiki:update beforehand

Proceed to generation only if the user instructs to continue.

### Step 3: Document Generation

Read all wiki pages of target entities and generate a document with the following structure:

```markdown
# <Theme>

Generated: YYYY-MM-DD
Sources: N llmwiki entities

## Overview
(Self-contained explanation of the overall picture of the theme)

## Components
(Structural explanation of related entities. Integrates each entity's Overview)

## Relationships
(Explains dependencies and interactions between entities)

## Notes
(Included when "needs review" flags or stale information exists)

## References
(List of llmwiki entities used)
```

### Step 4: Output

Present the generated document to the user.
If the user wishes to save it, write it to the specified path.

### Step 5: Log Entry

Append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] docs | <theme> (<entity count> entities)
```
