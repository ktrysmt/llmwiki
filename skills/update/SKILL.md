---
name: update
description: Run import, lint, and auto-fix as a single pipeline to keep .llmwiki/ in sync with source files. Use when the user wants to refresh the entire knowledge base end-to-end in one command.
argument-hint: "[path]"
allowed-tools: Read Edit Write Bash(python3 *) Bash(mkdir *)
---

# /llmwiki:update

Run import, lint, and fix as a single pipeline. Eliminates redundant preprocessing by running deterministic scripts once per boundary (before and after LLM ingestion).

## Prerequisites

- Python >= 3.12

## Arguments

`/llmwiki:update [path]`

The `path` argument is optional. Resolution order for the input directory:

1. Explicit argument: `/llmwiki:update <path>`
2. Saved config: `.llmwiki/config.json` -> `input_dir`
3. Default: project root (current working directory)

Inform the user which input directory is being used.

## Phase 0: Deterministic Preprocessing

### Step 0-0: Ensure Output Directory

```bash
mkdir -p .llmwiki/entities
```

### Step 0-1: Index Generation

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/makeindex.py --llmwiki-dir .llmwiki
```

### Step 0-2: Preprocessing

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_preprocess.py <input_dir> --llmwiki-dir .llmwiki > /tmp/llmwiki_preprocess.xml
```

### Step 0-3: Triage

Read `/tmp/llmwiki_preprocess.xml` and report:

- Number of new files, updated files, missing sources
- Total size (KB) of files to process
- Lint issue counts (orphan, broken links, stale, contradictions, etc.)

If `stats.new_files == 0` and `stats.updated_files == 0` and `stats.missing_sources == 0` and lint is clean and no decay candidates exist, report "no updates needed" and stop.

Otherwise, proceed automatically.

## Phase 1: LLM Ingestion

For each file in `new_files` and `updated_files`:

1. Load file content with Read
2. Determine `source_type` from the file path and content (primary / secondary / derived)
3. Extract new entities and relationships in addition to dictionary-matched entities (`known_entities`)
4. If a wiki page already exists, update it following the merge rules in `${CLAUDE_PLUGIN_ROOT}/skills/make/llmwiki/schema.md`. Otherwise create a new page from the template
5. Add new entities to `.llmwiki/entities.json` (lowercase kebab-case, aliases in both Japanese and English)
6. Add relationships bidirectionally (if adding A->B, also add B->A)
7. Record the file's SHA-256 hash in frontmatter `sources[].sha256` and the determination result in `sources[].source_type`
8. Attach fact-level provenance to each new or updated Key Fact: `- Fact [source: filename, source_type, YYYY-MM-DD]` (see `schema.md` Fact-Level Provenance section). Existing facts without provenance are left as-is (legacy)

For `updated_files` (files whose sha256 has changed):
- Update the `sha256` and `ingested` of the corresponding source in the existing page
- Update Key Facts and Overview based on content differences
- If contradicting previous descriptions, include both values with dates and add a "needs review" flag

Dormant page promotion:
- If the file corresponds to a page with `status: dormant`:
  1. Remove `status: dormant` from the frontmatter
  2. Remove `"status": "dormant"` from the corresponding entity in entities.json
  3. Add to Changelog: "YYYY-MM-DD: Reactivated to active (promotion due to new source ingestion)"
  4. Update frontmatter `updated` to today

For `missing_sources` (disappeared sources):
- Record "source disappeared" in the Source Files table of affected wiki pages
- Do not delete the page itself

Wiki page save location: `.llmwiki/entities/<category>/<entity-id>.md`

### Constraints
- Input directory files are read-only. Do not modify or delete
- Never delete wiki pages. Only flag stale/orphan
- The LLM does not resolve contradictory information. Retain both values with source dates and flag
- If a session cannot process all files, prioritize the most recent files and report the remaining count

### Partial Failure

If Phase 1 cannot complete all files, proceed to Phase 2 with processed files only. Report the unprocessed count in the final report.

## Phase 2: Deterministic Re-scan

### Step 2-1: Re-run Preprocessing

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_preprocess.py <input_dir> --llmwiki-dir .llmwiki > /tmp/llmwiki_lint.xml
```

### Step 2-2: Detect Decay Candidates

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_decay.py --llmwiki-dir .llmwiki --threshold-days 90
```

### Step 2-3: Synthesis Quality Check

For the top 3 updated pages, verify:
- Whether the Overview is accurate and self-contained
- Whether Relations are set bidirectionally
- Whether the Source Files table is correct

### Step 2-4: Assess Fix Targets

Read `/tmp/llmwiki_lint.xml` and decay output. If no contradictions, no decay candidates, and no promotion candidates exist, skip Phase 3 and Phase 4.

## Phase 3: Auto-fix

Apply fixes that do not require user approval.

### Step 3-1: Classify Contradictions

Read each contradiction page and classify:

- temporal: Different sources from different dates report different values. The newer one is likely correct
- scope: Describes different aspects of the same concept and is not actually contradictory
- genuine: Truly contradictory. Requires human judgment
- none: False positive. No actual contradiction exists

### Step 3-2: Apply Auto-resolvable Fixes

Apply immediately without user approval:

- temporal (both primary): Adopt the newer value. Log as "auto-resolved (temporal, primary+primary)"
- scope: Keep both values and remove the "needs review" flag. Log as "auto-resolved (scope)"
- none: Remove the "needs review" flag. Log as "auto-resolved (false positive)"

Dormant promotion candidates (references > 0 or recent source updates):
- Reactivate automatically: remove `status: dormant` from frontmatter and entities.json, add Changelog entry, update `updated` to today

When updating wiki pages:
1. Keep the adopted value with provenance tag: `- Adopted value [source: filename, source_type, YYYY-MM-DD]`
2. Record the rejected value in Changelog (e.g., "YYYY-MM-DD: Adopted value A, discarded value B (reason: temporal resolution)")
3. Remove the "needs review" flag
4. Update frontmatter `updated` to today
5. Provenance backfill: check all Key Facts for missing provenance tags. For facts without provenance, attempt to determine the source from the page's `sources[]` frontmatter. Add provenance where determinable; leave as-is where ambiguous

### Step 3-3: Propagation Check

After applying auto-fixes, check resolved values against related entities (1-hop via Relations):

1. Read the `related` field from frontmatter of each resolved page
2. Read Key Facts of each related entity
3. Semantically check if the adopted value contradicts any fact in related pages
4. If a new contradiction is found, add "needs review" flags to both pages and record in Changelog: "YYYY-MM-DD: Cross-entity contradiction detected during propagation check (entity-a vs entity-b)"

## Phase 4: Approval Batch

If no items require approval, skip this phase entirely.

### Items Requiring Approval

- temporal (mixed trust): Show diff. "Source from date X says A, source from date Y says B. Adopt the newer one?" Present the value from the higher-trust source as the priority candidate (primary > secondary > derived)
- genuine: Show diff. Present the higher-trust source value as priority candidate
- decay demotion (0 references, 90+ days not updated):
  - days_since_update > 180: Strongly recommend demotion
  - days_since_update > 90: Propose demotion

Present all diffs grouped by entity:

```
## Proposed changes

### <entity-id> (<type>)
--- .llmwiki/entities/<category>/<entity-id>.md
+++ .llmwiki/entities/<category>/<entity-id>.md (proposed)
@@ Key Facts @@
- ...
+ ...
@@ Changelog @@
+ ...

Approve? [y/n/all]
```

After user approval, apply changes following the same write rules as Step 3-2, then run propagation check (same as Step 3-3).

For decay demotion:
1. Add `status: dormant` to the wiki page frontmatter
2. Add `"status": "dormant"` to the corresponding entity in entities.json
3. Append to Changelog: "YYYY-MM-DD: Demoted to dormant (not updated for N days, 0 references)"

## Phase 5: Report and Log

### Step 5-1: Regenerate Index

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/makeindex.py --llmwiki-dir .llmwiki
```

### Step 5-2: Final Report

Report the following:

- Files processed (new / updated / missing sources)
- Wiki pages created / updated
- New entities added
- Contradictions: auto-resolved (temporal-auto: N, scope: N, none: N), user-resolved (temporal: N, genuine: N), remaining
- Decay: demoted N, promoted N
- Remaining lint issues (orphan, broken links, stale, uncovered, provenance gaps)
- Unprocessed files (if any)
- Contradiction statistics: highlight source files with 3+ contradiction pages as potentially unreliable sources

### Step 5-3: Persist Config

Save (or update) `.llmwiki/config.json` with the input directory used in this run.

If the file does not exist yet, initialize:

```json
{
  "input_dir": "<absolute path to input directory>"
}
```

If already exists, merge only `input_dir`. Preserve existing keys (`exclude_patterns`, etc.).

### Step 5-4: Log Entry

Append to `.llmwiki/log.md`:

```
## [YYYY-MM-DD] update | Processed <n> files, created <n>, updated <n>, auto-fixed <n>, user-fixed <n>, demoted <n>, promoted <n>, remaining <n>
```
