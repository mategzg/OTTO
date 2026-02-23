# LEARNINGS

## [LRN-20260223-001] correction

**Logged**: 2026-02-23T01:40:00-05:00
**Priority**: high
**Status**: promoted
**Area**: docs

### Summary
Repo-specific capability questions were answered from memory search only, missing existing repo evidence.

### Details
`memory_search` did not return plugin integration artifacts because they live under `docs/_inbox` and `state/*`. User corrected with explicit commits and files. Correct approach is dual-check: policy memory_search + repo artifact verification before conclusion.

### Suggested Action
Always run repo verification protocol for specific repo claims: check commits + artifact files before stating availability/integration status.

### Metadata
- Source: user_feedback
- Related Files: AGENTS.md, USER.md
- Tags: repo-verification, memory-gap, reliability
- Pattern-Key: verify.repo_claims.before_answer
- Recurrence-Count: 1
- First-Seen: 2026-02-23
- Last-Seen: 2026-02-23

### Resolution
- **Resolved**: 2026-02-23T01:40:00-05:00
- **Commit/PR**: pending
- **Notes**: Protocol promoted to AGENTS.md and USER.md.

---
