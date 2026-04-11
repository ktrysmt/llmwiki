---
name: fix
description: Resolve contradictions, demote decayed pages, and promote dormant pages in .llmwiki/ based on lint results. Use after /llmwiki:lint detects issues or when the user explicitly wants to clean up the knowledge base.
disable-model-invocation: true
allowed-tools: Read Edit Bash(python3 *)
---

# /llmwiki:fix

Fix issues detected by /llmwiki:lint: resolve contradictions, execute decay demotions, and promote dormant pages.

## Background

Research has shown that unresolved contradictions in context degrade LLM accuracy. Xie et al. (2024, "Knowledge Conflicts for LLMs: A Survey", EMNLP 2024) demonstrated that inter-context knowledge conflicts significantly reduce LLM reliability. Chroma Research's "Context Rot" study confirmed performance degradation across 18 frontier models as context noise increases. Unresolved contradictions in the wiki therefore degrade the accuracy of all LLM operations that reference it.

## Prerequisites

- Python >= 3.12

## Procedure

### Step 1: Collect Issues

If run following /llmwiki:lint, /tmp/llmwiki_lint.xml already exists.
In that case, skip preprocessing and use the existing output as-is.

Run preprocessing only if the file does not exist:

Resolve `input_dir`: read from `.llmwiki/config.json`, or fall back to the project root (cwd).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_preprocess.py <input_dir> --llmwiki-dir .llmwiki > /tmp/llmwiki_lint.xml
```

Retrieve contradiction pages from the `<contradictions>` section in `/tmp/llmwiki_lint.xml`.

### Step 2: Detect Decay/Promotion Candidates

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_decay.py --llmwiki-dir .llmwiki --threshold-days 90
```

Additionally, scan for promotion candidates from the preprocess XML output: pages with `status: dormant` but references > 0 or recent source updates.

If no contradictions, no decay candidates, and no promotion candidates are found, report "no issues to fix" and stop.

### Step 3: Classify Contradictions

If no contradiction pages are found, skip to Step 4.

Read each contradiction page and extract locations with "needs review" flags.
Classify contradictions as follows:

- temporal: Different sources from different dates report different values. The newer one is likely correct
- scope: Describes different aspects of the same concept and is not actually contradictory
- genuine: Truly contradictory. Requires human judgment
- none: False positive. No actual contradiction exists (misdetection, already resolved, etc.)

### Step 4: Propose Fixes

#### Contradictions

For each contradiction, present a resolution proposal:

- temporal (both primary): Auto-resolve by adopting the newer value. No user approval needed. Log as "auto-resolved (temporal, primary+primary)"
- temporal (mixed trust): "Source from date X says A, source from date Y says B. Adopt the newer one (Y: B)?" Show diff preview
- scope: Auto-resolve. Keep both values and remove the "needs review" flag. No user approval needed. Log as "auto-resolved (scope)"
- genuine: "Contradiction confirmed. Which value should be adopted? Or keep both?" Show diff preview. Present the value from the higher-trust source as the priority candidate (primary > secondary > derived)
- none: Auto-resolve. Remove the "needs review" flag. No user approval needed. Log as "auto-resolved (false positive)"

#### Decay Demotion

For pages with 0 references and not updated for 90+ days:
- days_since_update > 180: Strongly recommend demotion
- days_since_update > 90: Propose demotion

#### Promotion

For pages with `status: dormant` but references > 0 or recent source updates:
- Propose reactivation to active

### Step 5: Diff Preview

For items requiring user approval (temporal mixed-trust, genuine, decay, promotion), generate a unified diff showing the exact changes to each wiki page. Present diffs grouped by entity:

```
## Proposed changes

### amazon-ecs (genuine contradiction)
--- .llmwiki/entities/services/amazon-ecs.md
+++ .llmwiki/entities/services/amazon-ecs.md (proposed)
@@ Key Facts @@
- - CPU is 256 [source: config.json, primary, 2026-03-01]
-   vs 512 [source: deploy.yaml, primary, 2026-04-05] -- needs review
+ - CPU is 512 [source: deploy.yaml, primary, 2026-04-05]
@@ Changelog @@
+ - 2026-04-10: Adopted CPU=512, discarded CPU=256 (temporal)

Approve? [y/n]
```

Auto-resolved items (none, scope, temporal primary+primary) are listed as a summary without diff preview.

### Step 6: Apply

Apply auto-resolved items immediately. Apply user-approved items after confirmation.

#### 6a: Contradiction Resolution

When updating wiki pages:

1. Keep the adopted value in Key Facts with provenance tag: `- Adopted value [source: filename, source_type, YYYY-MM-DD]`
2. Record the rejected value in Changelog (e.g., "YYYY-MM-DD: Adopted value A, discarded value B (reason: temporal resolution)")
3. Remove the "needs review" flag
4. Update frontmatter `updated` to today
5. Provenance backfill: While editing the page, check all Key Facts for missing provenance tags. For facts without provenance, attempt to determine the source from the page's `sources[]` frontmatter (match by content and ingestion date). Add provenance where determinable; leave as-is where ambiguous

For none type:

1. Remove the "needs review" flag
2. Record in Changelog (e.g., "YYYY-MM-DD: Removed needs review flag as false positive")
3. Update frontmatter `updated` to today

#### 6b: Propagation Check

After applying resolutions in Step 6a, check whether the resolved values are consistent with related entities (1-hop via Relations).

For each resolved page:
1. Read the `related` field from frontmatter to get connected entity IDs
2. Read Key Facts of each related entity
3. Semantically check if the adopted value contradicts any fact in related pages
4. If a new contradiction is found, add "needs review" flags to both pages with the contradictory values and record in Changelog: "YYYY-MM-DD: Cross-entity contradiction detected during propagation check (entity-a vs entity-b)"
5. Report any new contradictions introduced by the resolution

This prevents cascade contradictions where resolving one conflict silently invalidates facts in related entities.

#### 6c: Decay Demotion

For user-approved decay candidates:
1. Add `status: dormant` to the wiki page frontmatter
2. Append to Changelog: "YYYY-MM-DD: Demoted to dormant (not updated for 90+ days, 0 references)"
3. Add `"status": "dormant"` to the corresponding entity in entities.json

Dormant entities are not excluded from entity matching in /llmwiki:import Phase 1,
but their reading priority is lowered in /llmwiki:query Step 2,
and they are flagged as stale in /llmwiki:docs Step 2.

#### 6d: Promotion

For user-approved promotion candidates:
1. Remove `status: dormant` from the wiki page frontmatter
2. Remove `"status": "dormant"` from the corresponding entity in entities.json
3. Append to Changelog: "YYYY-MM-DD: Reactivated to active (promotion due to references > 0)"
4. Update frontmatter `updated` to today

### Step 7: Report

- Total number of contradictions detected
- Number of contradictions resolved (by category)
- Number of remaining contradictions
- Change in delta (contradiction count before resolution -> after resolution)
- Number of pages demoted / promoted
- Contradiction statistics: report from `<contradiction-stats>` in the preprocessing XML if available. Highlight source files with the highest contradiction counts and categories with the most contradictions. If a source file contributes contradictions to 3 or more pages, flag it as a potentially unreliable source

### Step 8: Log Entry

Append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] fix | Resolved <count> (temporal:<n>, temporal-auto:<n>, scope:<n>, genuine:<n>, none:<n>), demoted <n>, promoted <n>, remaining <n>
```
