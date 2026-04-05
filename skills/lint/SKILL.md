# /llmwiki:lint

Check the health of .llmwiki/ and report issues.

## Prerequisites

- Python >= 3.12

## Procedure

### Step 1: Run Preprocessing

If `.llmwiki/` does not exist, report "llmwiki not yet created" and stop.

Resolve `input_dir`: read from `.llmwiki/config.json`, or fall back to the project root (cwd).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_preprocess.py <input_dir> --llmwiki-dir .llmwiki > /tmp/llmwiki_lint.xml
```

### Step 2: Detect Decay Candidates

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_decay.py --llmwiki-dir .llmwiki --threshold-days 90
```

### Step 3: Report

Read /tmp/llmwiki_lint.xml and report the following:

- orphan_pages: Pages not linked from any other page
- broken_links: [[wikilinks]] to non-existent entities
- stale_pages: Pages not updated for over 30 days
- uncovered_files: Files matching entities but not yet ingested
- contradictions: Count and page list of "needs review" flags
- decay_candidates: Pages with 0 references and not updated for 90+ days
  - days_since_update > 180: Strongly recommend demotion
  - days_since_update > 90: Propose demotion
- promotion_candidates: Pages with `status: dormant` but references > 0 or recent source updates

If all clean, report "no issues found".

### Step 4: Propose Fixes

If issues exist, propose corrective actions by category:
- orphan: Confirm whether to add to Relations of other pages
- broken_links: Propose creating the entity or fixing the link
- stale: Propose re-collecting source files
- uncovered: Propose re-running /llmwiki:make
- contradictions: Propose running /llmwiki:metabolize. Note that the /tmp/llmwiki_lint.xml output from lint can be used directly as input for metabolize
- decay_candidates: Propose demotion (requires user approval)
- promotion_candidates: Propose reactivation to active (requires user approval)

### Step 5: Execute Decay Demotion

For user-approved decay candidates:
1. Add `status: dormant` to the wiki page frontmatter
2. Append to Changelog: "YYYY-MM-DD: Demoted to dormant (not updated for 90+ days, 0 references)"
3. Add `"status": "dormant"` to the corresponding entity in entities.json

Dormant entities are not excluded from matching targets in /llmwiki:make Phase 1,
but their reading priority is lowered in /llmwiki:query Step 2,
and they are flagged as stale in /llmwiki:docs Step 2.

### Step 5b: Execute Promotion

For user-approved promotion candidates:
1. Remove `status: dormant` from the wiki page frontmatter
2. Remove `"status": "dormant"` from the corresponding entity in entities.json
3. Append to Changelog: "YYYY-MM-DD: Reactivated to active (promotion due to references > 0)"
4. Update frontmatter `updated` to today

### Step 6: Log Entry

Append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] lint | Detected <total issue count>, demoted <decay count>, promoted <promotion count>
```
