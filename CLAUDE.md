# llmwiki

## Rules

- Input directories are read-only. Do not modify or delete skill files
- All skills under `skills/` are bundled as one plugin. Installed together via `/plugin install`
- Never delete wiki pages. Only flag stale/orphan pages
- Contradictions are retained with both values + flag. The LLM does not resolve them. False positives (none) only have flags removed
- source_type trust order: primary > secondary > derived. Information inferred solely by LLM speculation (inferred) must not be written to the wiki
- Entity IDs use lowercase kebab-case
- Aliases include both Japanese and English
- If a session cannot process all files, prioritize the most recent files and report the remaining count
- `/llmwiki:fix` must not resolve contradictions without human approval
- `/llmwiki:lint` decay demotion and promotion must not be executed without human approval
- `/llmwiki:query` feedback must only be written to the wiki after obtaining human approval, unless the specific operation is enabled in `auto_approve` of `.llmwiki/config.json`
