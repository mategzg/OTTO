.PHONY: audit spec004-core-audit spec004-core-nightly

audit:
	python3 scripts/release_audit.py --root .

spec004-core-audit:
	python3 scripts/run_audit.py --spec spec004_core --date $$(date +%F)

spec004-core-nightly:
	python3 scripts/spec004_core_nightly.py
