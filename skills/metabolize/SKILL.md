# /llmwiki:metabolize

Detect contradictions ("needs review" flags) in .llmwiki/ and seek human judgment for resolution.

## Background

Research by DeltaZero has proven that LLM accuracy degrades exponentially with accumulated contradiction volume delta, following S = mu x e^(-delta x k). Unresolved contradictions in the wiki degrade the accuracy of all LLM operations that reference it.

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

Present a resolution proposal for each contradiction:

- temporal: "Source from date X says A, source from date Y says B. Adopt the newer one (Y: B)?"
- scope: "These are not contradictions but descriptions of different contexts. Keep both and remove the 'needs review' flag?"
- genuine: "Contradiction confirmed. Which value should be adopted? Or keep both?" (Present the value from the higher-trust source as the priority candidate. primary > secondary > derived)
- none: "This is not a contradiction (false positive). Remove the needs review flag?"

### Step 4: Apply

Resolve only contradictions approved by the user. When updating wiki pages:

1. Keep the adopted value in Key Facts
2. Record the rejected value in Changelog (e.g., "YYYY-MM-DD: Adopted value A, discarded value B (reason: temporal resolution)")
3. Remove the "needs review" flag
4. Update frontmatter `updated` to today

For none type:

1. Remove the "needs review" flag
2. Record in Changelog (e.g., "YYYY-MM-DD: Removed needs review flag as false positive")
3. Update frontmatter `updated` to today

### Step 5: Report

- Total number of contradictions detected
- Number of contradictions resolved (by category)
- Number of remaining contradictions
- Change in delta (contradiction count before resolution -> after resolution)

### Step 6: Log Entry

Append an entry to `.llmwiki/log.md` in the following format:

```
## [YYYY-MM-DD] metabolize | Resolved <count> (temporal:<n>, scope:<n>, genuine:<n>, none:<n>), remaining <n>
```
