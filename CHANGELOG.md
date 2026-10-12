# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog; versioning: SemVer.

## [0.1.1] - 2026-10-13

### Fixed / Revised (round-2 iteration)
- E003 now checks presence of the readiness 'checks' key, not truthiness - empty maps/arrays no longer false-flagged (A03/C12/C18)
- probe fixtures corrected from JSON-array to real JSONL (A25); A10 assertion rewritten (was malformed)

### Verification
- self_test re-run green after revisions: SUMMARY: PASS 67/67 (65 cases + 2 meta; >=60 gate met)
- CLI error contract re-verified (exit 0/1/2); four scaffold-v2 defenses inherited.

## [0.1.0] - 2026-10-13

### Added
- Core module `health_endpoint_spec.py`: validate (spec.json) / probe (--spec --samples JSONL, --json), pure standard library.
- argparse CLI with `--json` machine output and 0/1/2 exit-code contract.
- `self_test.py` inheriting scaffold-v2 defenses: SystemExit capture, unicode-safe
  regexes, `newline=""` fixtures, and the `SUMMARY: PASS n/n` last-line contract.
- README (Performance section with [Measured] numbers and in-repo repro commands),
  MIT LICENSE, ALIGNMENT.md (16-item rubric).
