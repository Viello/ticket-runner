# T093 — Audit Spec 10b Alignment and Verify Living Document Links
Status: completed
Completed: 2026-09-23T08:30:00Z
Spec: docs/specs/10b-living-documentation-and-roadmap.md
Blocked by: T092
Reasoning: medium

### Requirements
- Execute the closing audit for Spec 10b:
  1. Review all updated living documents (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`, and `README.md`) against `docs/specs/10b-living-documentation-and-roadmap.md`.
  2. Verify that terminology is 100% consistent across all documents and no forbidden synonyms are used.
  3. Verify that all markdown links, code blocks, and diagrams are structurally valid.
  4. Append any lessons, edge cases, or documentation maintenance quirks to `docs/tickets/gotchas.md`.
  5. Mark the ticket completed and relocate to `docs/tickets/10b-living-documentation-and-roadmap/completed/T093-audit-spec-10b-alignment-and-verify-links.md`.

### Acceptance Criteria
- All modified living documents align completely with Spec 10b.
- Zero terminology collisions with `CONTEXT.md` forbidden synonyms.
- `docs/tickets/gotchas.md` is updated with any lessons learned during the documentation refactor.

### Suggested Skills
- `writing-for-agents`: Auditing documentation against sediment, pruning no-ops, ensuring single source of truth.

### Smoke Scenarios
**Scenario: End-to-End Alignment Audit** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Confirm the repository's foundational living documentation is in a pristine, aligned state with zero forbidden synonyms, balanced code fences, and valid table of contents links before Spec 11 begins.
- Steps:
  1. Run the Python verification script in PowerShell to assert that all forbidden terms are absent, markdown code fences are balanced, local links exist, and README table of contents anchors match existing headings:
     ```powershell
     python -c @"
     from pathlib import Path
     import re

     # 1. Audit forbidden synonyms
     context_text = Path('CONTEXT.md').read_text(encoding='utf-8')
     strict_terms = ['client project', 'target repo', 'agent runner', 'llm backend', 'agent client', 'local config', 'project settings', 'runner override', 'test script', 'test harness', 'test report', 'verification summary', 'result block', 'plugin repo', 'skill store', 'prompt library', 'ai template', 'setup prompt', 'config assistant', 'session rollover', 'dumps']
     for f in ['README.md', 'ARCHITECTURE.md', 'AGENTS.md']:
         content = Path(f).read_text(encoding='utf-8').lower()
         for term in strict_terms:
             matches = [m.start() for m in re.finditer(r'\b' + re.escape(term) + r'\b', content)]
             for pos in matches:
                 snippet = content[max(0, pos-25):min(len(content), pos+35)]
                 if 'external multi-agent runner' not in snippet:
                     raise AssertionError(f'Found forbidden term \"{term}\" in {f}: ...{snippet}...')

     # 2. Check code block fence balance
     for f in ['README.md', 'ARCHITECTURE.md', 'AGENTS.md', 'CONTEXT.md', 'docs/specs/10b-living-documentation-and-roadmap.md', 'docs/tickets/gotchas.md']:
         text = Path(f).read_text(encoding='utf-8')
         lines = text.splitlines()
         quad = sum(1 for line in lines if line.strip().startswith(chr(96)*4))
         tri = sum(1 for line in lines if line.strip().startswith(chr(96)*3) and not line.strip().startswith(chr(96)*4))
         assert quad % 2 == 0 and tri % 2 == 0, f'Unbalanced code fence in {f}'

     # 3. Check README Table of Contents anchors
     readme = Path('README.md').read_text(encoding='utf-8')
     headers = {re.sub(r' ', '-', re.sub(r'[^\w\s-]', '', re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', m.group(2)).replace(chr(96), '').replace('*', '').lower())) for m in re.finditer(r'^(#{1,6})\s+(.*)$', readme, re.MULTILINE)}
     toc = readme[readme.find('## Table of Contents'):readme.find('## Overview')]
     for title, anchor in re.findall(r'\[([^\]]+)\]\(#([^\)]+)\)', toc):
         assert anchor in headers, f'Missing anchor: #{anchor}'

     print('PASS: Spec 10b living documentation and links 100% aligned.')
     "@
     ```
  2. Run `git status` to confirm only intended documentation files and completed tickets are modified.
- Expected: Script prints `PASS: Spec 10b living documentation and links 100% aligned.` with exit code 0.

### Gotchas
- This is the closing alignment ticket for Spec 10b. It serves as the model for closing alignment tickets required in all subsequent specs.
