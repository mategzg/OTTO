.PHONY: audit

audit:
	python3 scripts/release_audit.py --root .
