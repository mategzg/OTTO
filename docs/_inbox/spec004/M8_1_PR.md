# SPEC-004 M8.1: Final Certification Hardening

Status: IN_PROGRESS
Milestone: M8.1 / PR-10

## Scope
- Harden `scripts/run_audit.py` with fail-fast clean gate, ordered all-in-one flow, zip fallback via python, and final checksum outputs.
- Add unified no-leak suite runner (`scripts/no_leak_unified.py`).
- Defer integrated live smoke to a future phase (out of current certification scope).

## Acceptance
- Single command: `python3 scripts/run_audit.py --all --date <YYYY-MM-DD>`.
- Hard fail on dirty repo.
- Emits GO/NO-GO with explicit reason and reproducible artifacts.
