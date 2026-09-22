# Production Recovery Drill Evidence — 2026-09-22

This directory preserves the non-sensitive evidence from the accepted Prime
backup and isolated-restore drill `20260922T175546Z`.

The backup payloads and detailed database/output manifests remain in the
root-only Prime directory
`/root/geovis-backups/production-drill-20260922T175546Z`. They are not committed
because they contain production data, filenames, identifiers, and account or
project metadata.

Included evidence:

- `result.txt`: acceptance flags and isolated resource names.
- `timings.env`: measured backup and restore durations.
- `checksums.sha256`: hashes of the PostGIS dump and output archive.
- `restored-content-validation.json`: restored filesystem/metadata checks.
- `restored-api-validation.json`: isolated dashboard API checks.
- `evidence-hashes.sha256`: hashes of committed evidence and the matching
  source manifests retained on Prime.
- `month-end-tests.txt`: complete-suite result on merged `main`.
- `live-validation.json`: post-drill live deployment checks and the identified
  deployment-parity gap.

Database, output-manifest, and production-state evidence hashes are identical
for production-before, production-after, and restored copies. This proves the
comparison artifacts matched without publishing their sensitive contents.
