# /llmwiki:metabolize

Detect contradictions ("needs review" flags) in .llmwiki/ and seek human judgment for resolution.

## Background

Research has shown that unresolved contradictions in context degrade LLM accuracy. Xie et al. (2024, "Knowledge Conflicts for LLMs: A Survey", EMNLP 2024) demonstrated that inter-context knowledge conflicts significantly reduce LLM reliability. Chroma Research's "Context Rot" study confirmed performance degradation across 18 frontier models as context noise increases. Unresolved contradictions in the wiki therefore degrade the accuracy of all LLM operations that reference it.

## Prerequisites

- Python >= 3.12

## Procedure

### Step 1: Collect Contradictions

If run following /llmwiki:lint, /tmp/llmwiki_lint.xml already exists.
In that case, skip preprocessing and use the existing output as-is.

Run preprocessing only if the file does not exist:

Resolve `input_dir`: read from `.llmwiki/config.json`, or fall back to the project root (cwd).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/make/scripts/llmwiki_preprocess.py <input_dir> --llmwiki-dir .llmwiki > /tmp/llmwiki_lint.xml
```

Retrieve contradiction pages from the `<contradictions>` section in `/tmp/llmwiki_lint.xml`.
If no pages are found, report "no contradictions" and stop.

### Step 2: Classify Contradictions

Read each contradiction page and extract locations with "needs review" flags.
Classify contradictions as follows:

- temporal: Different sources from different dates report different values. The newer one is likely correct
- scope: Describes different aspects of the same concept and is not actually contradictory
- genuine: Truly contradictory. Requires human judgment
- none: False positive. No actual contradiction exists (misdetection, already resolved, etc.)

### Step 3: Propose Resolution

Check `.llmwiki/config.json` for `auto_approve.metabolize_temporal_primary` (default: false).

For each contradiction, present a resolution proposal:

- temporal (auto-approve eligible): If `metabolize_temporal_primary` is true AND both sources are primary, auto-resolve by adopting the newer value. Log as "auto-resolved (temporal, primary+primary)". If either source is secondary or derived, fall back to user approval: "Source from date X says A, source from date Y says B. Adopt the newer one (Y: B)?"
- temporal (standard): "Source from date X says A, source from date Y says B. Adopt the newer one (Y: B)?"
- scope: "These are not contradictions but descriptions of different contexts. Keep both and remove the 'needs review' flag?"
- genuine: "Contradiction confirmed. Which value should be adopted? Or keep both?" (Present the value from the higher-trust source as the priority candidate. primary > secondary > derived)
- none: "This is not a contradiction (false positive). Remove the needs review flag?"

### Step 4: Apply

Resolve only contradictions approved by the user. When updating wiki pages:

1. Keep the adopted value in Key Facts with provenance tag: `- Adopted value [source: filename, source_type, YYYY-MM-DD]`
2. Record the rejected value in Changelog (e.g., "YYYY-MM-DD: Adopted value A, discarded value B (reason: temporal resolution)")
3. Remove the "needs review" flag
4. Update frontmatter `updated` to today
5. Provenance backfill: While editing the page, check all Key Facts for missing provenance tags. For facts without provenance, attempt to determine the source from the page's `sources[]` frontmatter (match by content and ingestion date). Add provenance where determinable; leave as-is where ambiguous

For none type:

1. Remove the "needs review" flag
2. Record in Changelog (e.g., "YYYY-MM-DD: Removed needs review flag as false positive")
3. Update frontmatter `updated` to today

### Step 4b: Propagation Check

After applying resolutions in Step 4, check whether the resolved values are consistent with related entities (1-hop via Relations).

For each resolved page:
1. Read the `related` field from frontmatter to get connected entity IDs
2. Read Key Facts of each related entity
3. Semantically check if the adopted value contradicts any fact in related pages
4. If a new contradiction is found, add "needs review" flags to both pages with the contradictory values and record in Changelog: "YYYY-MM-DD: Cross-entity contradiction detected during propagation check (entity-a vs entity-b)"
5. Report any new contradictions introduced by the resolution

This prevents cascade contradictions where resolving one conflict silently invalidates facts in related entities.

### Step 5: Report

- Total number of contradictions detected
- Number of contradictions resolved (by category)
- Number of remaining contradictions
- Change in delta (contradiction count before resolution -> after resolution)
- Contradiction statistics: report from `<contradiction-stats>` in the preprocessing XML if available. Highlight source files with the highest contradiction counts and categories with the most contradictions. If a source file contributes contradictions to 3 or more pages, flag it as a potentially unreliable source

### Step 6: Log Entry

Append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] metabolize | Resolved <count> (temporal:<n>, temporal-auto:<n>, scope:<n>, genuine:<n>, none:<n>), remaining <n>
```
