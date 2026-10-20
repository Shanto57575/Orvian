---
name: review-change
description: Independently review a code change for bugs, security issues, unsafe AI tool use, migrations, tests and performance. Use before merge or after implementation.
---
# Review change
1. Read `AGENTS.md`, `docs/PROJECT.md`, `docs/REVIEW_CHECKLIST.md` and the relevant diff.
2. Focus on concrete defects and regressions, not speculative style preferences.
3. Verify security and AI-specific risks: tool authorization, prompt injection, retrieval grounding, secrets, rate limits, user-data isolation.
4. Run relevant automated checks when possible; explicitly report any not run.
5. Report findings ordered by severity with file/line, scenario, risk, and minimal fix. If none, say no findings and list residual risks.
6. Do not alter files during review unless asked; do not approve or merge unverified changes.
