---
name: lint
description: Audit .llmwiki/ knowledge base health and report issues like orphan pages, broken links, stale pages, contradictions, cross-entity contradictions, provenance gaps, and decay candidates. Use when the user wants to check wiki state or before running /llmwiki:update.
allowed-tools: Read Edit Bash(python3 *)
---

# /llmwiki:lint

Check the health of .llmwiki/ and report issues.

## Environment

```!
python3 --version 2>&1 || echo "FATAL: python3 not found. Install Python >= 3.12."
echo "LLMWIKI_SCRIPTS=$(cd "${CLAUDE_SKILL_DIR}/../import/scripts" 2>/dev/null && pwd || echo NOT_FOUND)"
```

## Wiki State

```!
if [ -d .llmwiki ]; then
  entity_count=$(find .llmwiki/entities -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  echo "status: initialized"
  echo "entity_pages: ${entity_count}"
  echo "config: $(cat .llmwiki/config.json 2>/dev/null || echo 'none')"
  echo "last_log:"
  tail -3 .llmwiki/log.md 2>/dev/null || echo "  (empty)"
else
  echo "status: not_initialized"
fi
```

If the Environment section shows FATAL or LLMWIKI_SCRIPTS=NOT_FOUND, inform the user and stop.
If Wiki State shows not_initialized, report "llmwiki not yet created" and stop.

## Prerequisites

- Python >= 3.12

## Procedure

### Step 1: Run Preprocessing

If `.llmwiki/` does not exist, report "llmwiki not yet created" and stop.

Resolve `input_dir`: read from `.llmwiki/config.json`, or fall back to the project root (cwd).

```bash
python3 ${LLMWIKI_SCRIPTS}/llmwiki_preprocess.py <input_dir> --llmwiki-dir .llmwiki > /tmp/llmwiki_lint.xml
```

### Step 2: Detect Decay Candidates

```bash
python3 ${LLMWIKI_SCRIPTS}/llmwiki_decay.py --llmwiki-dir .llmwiki --threshold-days 90
```

### Step 3: Report

Read /tmp/llmwiki_lint.xml and report the following:

- orphan_pages: Pages not linked from any other page
- broken_links: [[wikilinks]] to non-existent entities
- stale_pages: Pages not updated for over 30 days
- uncovered_files: Files matching entities but not yet ingested
- contradictions: Count, page list, and urgency score of "needs review" flags (sorted by urgency descending). Urgency = days_since_flagged x impact_weight. Thresholds:
  - urgency > 360: Critical -- strongly recommend immediate resolution
  - urgency > 180: High -- recommend running /llmwiki:update
  - urgency > 0: Normal -- report for awareness
- decay_candidates: Pages with 0 references and not updated for 90+ days
  - days_since_update > 180: Strongly recommend demotion
  - days_since_update > 90: Propose demotion
- promotion_candidates: Pages with `status: dormant` but references > 0 or recent source updates

- cross_entity_contradictions: Potential contradictions between related entities. The preprocessing XML provides `<cross-entity-pairs>` containing Key Facts for each pair of related entities. Read each pair and semantically check if facts from entity A contradict facts from entity B (e.g., entity A says "DB version is 14" while entity B says "DB version is 15"). Report only genuine semantic contradictions, not mere differences in scope or context

- contradiction_stats: Summary of contradictions by source file and category (from `<contradiction-stats>` in XML). Highlight source files with disproportionately high contradiction counts as potential low-quality sources
- provenance_gaps: Count of Key Facts missing provenance tags (from `<provenance-gaps>` in XML). Report total facts without provenance and the pages with the most gaps. This is informational only -- provenance is backfilled gradually through make and fix operations

If all clean, report "no issues found".

### Step 4: Propose Fixes

If issues exist, propose corrective actions by category:
- orphan: Confirm whether to add to Relations of other pages
- broken_links: Propose creating the entity or fixing the link
- stale: Propose re-collecting source files
- uncovered: Propose re-running /llmwiki:update
- contradictions: Propose running /llmwiki:update. Note that the /tmp/llmwiki_lint.xml output from lint can be used directly as input for the fix phase of update
- cross_entity_contradictions: For each detected cross-entity contradiction, propose running /llmwiki:update
- decay_candidates: Propose running /llmwiki:update
- promotion_candidates: Propose running /llmwiki:update

### Step 5: Log Entry

Append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] lint | Detected <total issue count>
```
