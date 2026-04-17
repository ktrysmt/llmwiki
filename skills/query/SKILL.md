---
name: query
description: Answer questions by searching the .llmwiki/ knowledge base. Cites entity sources with [[wikilinks]] and flags needs-review information. Use when the user asks questions about content the wiki covers.
argument-hint: "<question>"
allowed-tools: Read Edit Write
---

# /llmwiki:query

Query the knowledge base accumulated in .llmwiki/ and get answers.

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

`/llmwiki:query <question>`

## Procedure

### Step 1: Search

1. Read `.llmwiki/index.xml`
2. Identify entities related to the question from the index
3. Also reference aliases in `.llmwiki/entities.json` to absorb notation variations

### Step 2: Collection

1. Read wiki pages of related entities (up to 10 pages)
2. Follow Relations by one hop and also read related pages
3. Explicitly note pages that have "needs review" flags
4. Lower the reading priority of pages with `status: dormant` in frontmatter

### Step 3: Answer

1. Answer the question based on collected information
2. Cite source entity-ids in `[[entity-id]]` format in the answer
3. If the answer includes information with "needs review" flags, explicitly state this

### Step 4: Feedback (optional)

If the following are discovered during the answering process, propose to the user and only update the wiki if the user approves. Exception: 4e (Saving Synthesized Answer) is saved without asking — see its section for details.

#### 4a: Adding Relationships

Discovery: Entities A and B have an unregistered relationship.

Write procedure:
1. Read page A
2. Add B to frontmatter `related`
3. Append `[[B]] -- Description of relationship` to `## Relations`
4. Similarly add A to page B (bidirectional)
5. Update frontmatter `updated` to today on both pages
6. Append to `## Changelog` on both pages

#### Wiki Page Schema

```!
cat "${CLAUDE_SKILL_DIR}/../../shared/schema.md" 2>/dev/null || echo "ERROR: schema.md not found"
```

#### 4b: New Entity Proposal

Discovery: A concept not matching any existing entity was needed for the answer.

Write procedure:
1. Create a new page at `.llmwiki/entities/<category>/<entity-id>.md` following the template in the Wiki Page Schema section below
2. Add to the corresponding category in `.llmwiki/entities.json` (lowercase kebab-case, aliases in both Japanese and English)
3. Bidirectionally add to Relations of related existing pages

#### 4c: Contradiction Discovery

Discovery: A description in an existing page contradicts another page or the answer content.

Write procedure:
1. Read the relevant page
2. Include both values with provenance in `## Key Facts` and add a "needs review" flag: `- Value A [source: file-a, type, YYYY-MM-DD] vs Value B [source: file-b, type, YYYY-MM-DD] -- needs review`. If provenance cannot be determined for either value, omit the `[source: ...]` tag for that value
3. Update frontmatter `updated` to today
4. Append to `## Changelog`: "YYYY-MM-DD: Contradiction detected (value A vs value B), added needs review flag"

#### 4d: Dormant Page Promotion

Discovery: A page with `status: dormant` was needed for the answer.

Proposal: "This page is dormant but was used in the answer. Would you like to reactivate it to active?"

Write procedure:
1. Remove `status: dormant` from the page's frontmatter
2. Remove `"status": "dormant"` from the corresponding entity in entities.json
3. Append to Changelog: "YYYY-MM-DD: Reactivated to active (promotion due to re-reference in query)"
4. Update frontmatter `updated` to today

#### 4e: Saving Synthesized Answer to Syntheses (no approval required)

Condition: When the answer spans multiple entities with analysis/comparison that has value as a standalone page.

Always save without asking for approval, then inform the user after the fact. This is an exception to the Step 4 approval rule.

Write procedure:
1. Save as `.llmwiki/syntheses/<kebab-case-theme>.md`
2. Record `source_type: derived`, `generated: YYYY-MM-DD`, `source_entities: [entity-id, ...]` in the document's frontmatter

#### Log Entry

If wiki writes were performed in Step 4, append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] query | <type of 4a/4b/4c/4d/4e executed and target entities>
```
