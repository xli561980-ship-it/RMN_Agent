# Changelog

## 2026-06-01

### Added

- Added evaluation tooling for golden runs, run comparison, corpus audits, and parse audits.
- Added committed evaluation reports under `eval/reports/`.
- Added regression tests for recursive ingest scanning and zero-chunk ingest records.

### Changed

- Switched the default ingest path to local parsing, with LlamaParse kept optional because the paid credit limit blocked practical use.
- Made ingest scan `data/papers/` and `data/manuals/` recursively.
- Repaired stale processed records that had no matching Chroma chunks.
- Stopped marking zero-chunk parses as successful, so failed parses can be retried.
- Tightened fusion citation instructions and set fusion generation temperature to `0.0`.

### Results

- Chroma coverage after incremental ingest: `483` sources and `11715` chunks.
- Stale processed-without-Chroma records: `87` to `0`.
- Final golden route/source checks: `5/5`.
- Final citation validation: `20%` baseline to `100%`.

### Notes

- Raw `eval/runs/*.jsonl` files remain local-only because they can contain retrieved corpus snippets and generated answer text.
