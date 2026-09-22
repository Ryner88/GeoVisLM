# Production Backup, Restore, and Retention

This document defines the GeoVisLM production backup policy and records the
latest recovery drill. It applies to the Prime deployment at
`/opt/geovis_lm`.

## Protected State

Each production backup set must contain:

- A custom-format `pg_dump` of the `geovis_lm` PostGIS database.
- A compressed archive of the complete `geovis_lm_geovis_outputs` volume.
- SHA-256 checksums for both backup payloads.
- Database and output manifests captured before backup and after restore.
- The deployed Git commit, database cluster identifier, production container
  identities, health states, and volume mounts.
- Backup/restore timings and application-level validation results.

The output volume is essential. The current production release stores project,
run, job, report, and artifact metadata there; PostGIS currently contains the
spatial extensions and reference data but no GeoVisLM application tables.

Production backup sets are stored under `/root/geovis-backups/` with directory
mode `0700` and file mode `0600`. They can contain account and project data and
must never be committed to Git or placed in a public object store.

## Backup Procedure

Run the version-controlled drill as root on Prime:

```bash
cd /opt/geovis_lm
VERIFY_SCRIPT=/opt/geovis_lm/scripts/backup_restore_verify.py \
API_VERIFY_SCRIPT=/opt/geovis_lm/scripts/backup_restore_api_verify.py \
scripts/production_backup_restore_drill.sh
```

The script uses transaction-consistent `pg_dump`, reads the production output
volume without writing to it, and rejects a backup if the production database
fingerprint or output manifest changes while the archives are being created.

## Isolated Restore Procedure

The drill creates uniquely named scratch PostGIS and output volumes. The
scratch database container uses `--network none`; it never joins the production
Compose network. The restored application container also uses `--network none`,
a read-only root filesystem, and a read-only restored output mount.

Acceptance requires all of the following:

- Backup SHA-256 checksums pass.
- Restored and production database extension/table fingerprints match.
- Restored and production output manifests match by path, mode, byte size, and
  SHA-256 digest.
- Every JSON metadata file parses.
- Project/run relationships and every `/app/outputs/` metadata reference
  resolve in the restored tree.
- The isolated dashboard API reads every project and run.
- Every registered output downloads through the isolated API with the expected
  byte size and SHA-256 digest.
- Production cluster, volume, container, database, and output fingerprints are
  unchanged before and after the drill.

Scratch containers and volumes are removed by an exit trap on success or
failure. The production Compose project is never stopped, recreated, or given
the scratch volumes.

## Retention Rules

- Keep successful ad-hoc and restore-drill backup payloads for 90 days.
- Keep the newest three successful backup sets even if the 90-day window has
  elapsed, until a newer set has passed an isolated restore.
- Keep the non-sensitive drill record in Git permanently.
- Remove incomplete/failed backup sets after the failure has been diagnosed
  and a later drill has passed.
- Maintain an encrypted, access-controlled off-host copy before relying on the
  backup for host-loss recovery. The on-host copy validates recoverability but
  does not protect against total Prime host loss.
- Review this policy after material schema, storage, or regulatory changes.

## Cleanup Procedure

1. Confirm the candidate backup directory is exactly beneath
   `/root/geovis-backups/` and matches `production-drill-<UTC timestamp>`.
2. Confirm a newer backup has `status=pass`, valid payload checksums, and a
   completed isolated-restore record.
3. Confirm no container or volume name from the candidate set remains active.
4. Remove only the selected expired or incomplete backup directory.
5. Never run `docker compose down --volumes`, remove
   `geovis_lm_geovis_postgis`, or remove `geovis_lm_geovis_outputs` as part of
   backup cleanup.
6. Record material cleanup in the operations log.

## Validated Drill: 2026-09-22

Prime backup set:

```text
/root/geovis-backups/production-drill-20260922T175546Z
```

Durations:

| Operation | Duration |
| --- | ---: |
| Database backup | 0.466 s |
| Output archive | 0.088 s |
| Total backup | 0.563 s |
| Isolated database/output restore | 10.612 s |

Restored content:

| Check | Result |
| --- | ---: |
| Files | 86 |
| Total uncompressed bytes | 907,421 |
| Projects | 6 |
| Runs | 6 |
| Jobs | 6 |
| Reports | 6 |
| Run artifact files | 66 |
| Parsed JSON files | 26 |
| Resolved output references | 156 |
| Missing references | 0 |
| Orphan runs | 0 |

Isolated application verification:

| Check | Result |
| --- | ---: |
| API health | `ok` |
| Projects read through API | 6 |
| Runs read through API | 6 |
| Registered downloads verified | 36 |
| Download bytes verified | 470,202 |
| Report/metadata downloads verified | 6 |

Integrity result:

- PostGIS dump SHA-256:
  `bb5445e84cadd8acc31b2be8f7c87c55700bd388b1c4d640679576a1b262bde5`
- Output archive SHA-256:
  `aa0ebe5505373fc38a754968720d7abd6c7d91e4d7c99a8ab63803c0c23bfa11`
- Database fingerprint: match.
- Output manifest: match.
- Backup payload checksums: pass.
- Isolated dashboard API validation: pass.
- Scratch resources after exit: none.
- Production services after drill: dashboard, worker, and database healthy;
  `/readyz` returned ready.
- Production mutation check: pass. The Git commit, database cluster identifier,
  named volumes, production container identities/images/mounts, database
  fingerprint, and output manifest were unchanged. Only the new root-only
  backup set was added outside the production data volumes.
- Cleanup check: pass. Superseded/incomplete drill directories, temporary
  scripts, helper image, scratch containers, and scratch volumes created during
  validation were removed. The accepted backup set above was retained.
