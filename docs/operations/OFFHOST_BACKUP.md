# Encrypted Off-Host Backup Replication

This runbook implements GitHub issue #5 without changing GeoMiniLM model or
recommendation approval gates. The selected target is a private Backblaze B2
bucket owned by GeoVisLM operations. Repository files are installation
templates only; production scheduling must not be enabled until every live
acceptance test below passes.

## Protected data and acceptance boundary

Each replication starts with `production_backup_restore_drill.sh`. The source
set is accepted only if it contains and verifies:

- the PostGIS custom-format dump and database fingerprint;
- the complete output-volume archive and path/mode/size/SHA-256 manifest;
- project, run, job, metadata, report, and registered-output records;
- resolved metadata references and project/run relationships;
- isolated API reads of every project and run; and
- downloads of every registered output with matching size and SHA-256 digest.

`offhost_backup.py` rejects sets that lack any of those positive coverage
counts, have broken references, have a failed drill result, or fail their
payload checksums. It streams the set through `age` and writes only ciphertext
to its staging directory before upload. The ciphertext and a SHA-256 sidecar
are uploaded to B2, downloaded to a new temporary directory, and checked again
before the run succeeds. An age file's authenticated encryption supplies the
additional decryption-time tamper check.

## Required independent prerequisites

Provision all of these before a live run:

1. A private B2 bucket and a `geovislm/production/` object prefix. GeoVisLM
   operations is the documented owner.
2. A Prime replication key restricted to that one bucket and exact prefix,
   with only `listBuckets`, `listFiles`, `readFiles`, `writeFiles`, and
   `deleteFiles`. Do not use the B2 master key. The delete capability is used
   only by the retention operation after a verified upload.
3. A separate recovery key restricted to the same bucket and prefix, with only
   `listBuckets`, `listFiles`, and `readFiles`. Store it only on the independent
   recovery host.
4. A dedicated native age key. Prime receives only its public `age1...`
   recipient. Keep the identity offline or in the recovery environment's
   secret store, never on Prime, in B2, or beside backup payloads. Its file must
   be owned appropriately and mode `0600` or stricter.
5. An HTTPS operator-alert webhook whose delivery can be observed and
   acknowledged.
6. An independent recovery host with Docker, `postgis/postgis:16-3.4`, a
   GeoVisLM application image built from the production commit recorded in the
   backup, that commit available in the local Git repository, `age`, B2 CLI v4,
   `jq`, and enough scratch storage. It must not mount, copy, or read Prime's
   `/root/geovis-backups` directory.

Backblaze's CLI needs `listBuckets` to resolve a provided bucket name. The
runtime preflight reads the authorized account restrictions and rejects a key
that is not bucket/prefix scoped, lacks required capabilities, or has bucket or
key administration capabilities.

Install `/etc/geovis-lm/offhost-backup.env` from
`deploy/offhost-backup.env.example`, replace every placeholder, set ownership
to `root:root`, and set mode `0600`. Never print, shell-trace, commit, or pass
credentials as command arguments. The B2 CLI reads credentials from
`B2_APPLICATION_KEY_ID` and `B2_APPLICATION_KEY`; its account cache is kept in
the private systemd runtime directory.

Install `/etc/geovis-lm/offhost-alert.env` from the separate alert example with
the same ownership and mode. It contains the webhook configuration but no B2
credentials, so the systemd failure handler cannot read storage credentials.

## Manual validation before scheduling

Run the unit/regression suite first. Then test delivery to the real operator
channel; a successful HTTP response alone is insufficient—have an operator
confirm receipt.

```bash
sudo systemd-run --wait --pipe \
  --property=EnvironmentFile=/etc/geovis-lm/offhost-backup.env \
  --working-directory=/opt/geovis_lm \
  /opt/geovis_lm/scripts/offhost_backup.py alert-test
```

Run one complete backup and replication manually:

```bash
sudo systemd-run --wait --pipe \
  --property=EnvironmentFile=/etc/geovis-lm/offhost-backup.env \
  --working-directory=/opt/geovis_lm \
  /opt/geovis_lm/scripts/run_offhost_backup.sh
```

Record the object key and ciphertext SHA-256 from the JSON result. The command
does not print B2 credentials, the alert URL, or age private material. A failure
retries each B2 operation four times with exponential backoff and attempts an
operator alert. Systemd also invokes the alert unit if the service fails before
the replication command starts.

## Restore using only B2

On the independent recovery host, configure the read-only recovery B2 key and
bucket/prefix values. Do not configure `AGE_RECIPIENT` or copy Prime's
replication key. Place the age identity outside the recovery workspace and
outside any backup directory with mode `0600`.

Build or obtain the application image from the backup's recorded production
commit. A trusted build from that checkout can carry its revision label:

```bash
docker build --build-arg GEOVIS_SOURCE_COMMIT="$(git rev-parse HEAD)" \
  -t geovis_lm_app:recovery .
```

Set `RECOVERY_APP_IMAGE` to that image reference.
The restore checks the recorded commit against the local Git repository and
the image's `org.opencontainers.image.revision` label, then runs the resolved
immutable image ID. A `latest` tag alone does not establish release identity.

```bash
export GEOVIS_RECOVERY_ENVIRONMENT=independent
export RECOVERY_APP_IMAGE=geovis_lm_app:recovery
sudo --preserve-env=GEOVIS_RECOVERY_ENVIRONMENT,RECOVERY_APP_IMAGE \
  /path/to/GeoVisLM/scripts/offhost_restore_drill.sh \
  --object-key geovislm/production/production-drill-YYYYMMDDTHHMMSSZ.tar.age \
  --identity-file /secure/secrets/geovis-offhost-age-identity.txt
```

The drill downloads ciphertext and its checksum directly from B2, verifies the
ciphertext, decrypts into a new recovery workspace, validates the source set,
and restores into uniquely named Docker volumes and network-isolated
containers. Docker Desktop can run this flow because extraction and output
validation access the volume only inside temporary containers; the host never
uses Docker's volume mountpoint. The recovery operator needs Docker access and
write access to `RECOVERY_ROOT` and can run without root if those are available.
It compares the restored database and outputs to the embedded
production fingerprints, parses all restored metadata, checks relationships,
and repeats the isolated API/download verification. Scratch containers and
volumes are removed on exit. A passing result is written only after Docker
confirms both scratch containers and both volumes are absent; the result is
recorded in `scratch-cleanup.json`. Preserve the restricted recovery evidence
directory until non-sensitive evidence has been reviewed and recorded.

If a fingerprint query fails, `fingerprint-queries.tsv` identifies the table,
time, and exit status. Its stderr file remains in the evidence directory (for
example, `fingerprint-public.spatial_ref_sys.stderr`). Before cleanup, the
failure trap saves timestamped PostgreSQL logs in `postgresql.log`, plus the
database and application container states and Docker server response in
`container-state.json`. A Docker timeout is recorded explicitly. A failed
fingerprint, missing API validation, or unverified cleanup cannot produce a
passing recovery result. On a passing run, retain `restored-db.tsv`,
`restored-outputs.tsv`, `restored-content-validation.json`,
`restored-api-validation.json`, and `scratch-cleanup.json` as the issue #5
acceptance evidence.

The restore waits for PostGIS's `PostgreSQL init process complete; ready for
start up.` log marker and then checks `pg_isready`. The image's temporary
initialization server can answer `pg_isready` before it shuts down, so that
check alone is insufficient. The latest polling output is saved in
`postgresql-startup.log`.

The live acceptance record must identify the independent host without exposing
credentials, show that Prime's backup directory was neither mounted nor read,
and include the B2 object version/key, ciphertext digest, restore result,
coverage counts, alert receipt, and retention test result.

The validated 2026-10-18 B2-only restore and its private evidence hashes are
recorded in [`evidence/offhost-recovery-20261018/README.md`](evidence/offhost-recovery-20261018/README.md).
Alert receipt and retention deletion remain separate acceptance items.

## Retention and deletion test

The client policy retains every verified set for 90 days and always retains the
newest three verified sets. Retention runs only after a new upload has passed
the download-and-checksum check. The client uses the UTC timestamp in the
object name and deletes only when it is strictly older than 90 days and outside
the newest three. An incomplete ciphertext/checksum pair or a future-dated
backup name blocks retention. Object names and matching sidecars alone do not
prove a backup was restored; the operator must confirm the source drill and
upload/readback validation before approving a manual apply. Preview production
candidates without `--apply`:

```bash
sudo systemd-run --wait --pipe \
  --property=EnvironmentFile=/etc/geovis-lm/offhost-backup.env \
  --working-directory=/opt/geovis_lm \
  /opt/geovis_lm/scripts/offhost_backup.py retention
```

For live acceptance, prepare disposable age-encrypted fixtures with
`scripts/prepare_retention_fixtures.py`. It creates separate `cutoff` and
`minimum` scenarios, each with archive/checksum pairs and a manifest of the
one expected deletion and retained objects. The live cutoff fixtures sit a
full day either side of the 90-day boundary so the expected result remains
stable while the test runs; an exact-cutoff unit test covers the strict
comparison. For a single-prefix acceptance preview, use `--single-canary` to
create ten direct-child pairs, one expired candidate, and nine retained pairs
under the exact canary prefix. Upload one scenario at a time under its
dedicated test prefix and use a B2 key restricted to that exact prefix. The
production-scoped key will not pass the client's exact-prefix preflight for a
nested test prefix. A production retention run ignores nested canary objects;
direct-child incomplete pairs and future-dated names still block it.

Before each apply, the client rechecks the exact bucket and key prefix, lists
all B2 versions, verifies the selected version IDs, and recomputes the 90-day
and newest-three decision. It rejects multiple versions, hide markers, and
unexpected direct-child objects. It writes a root-only recovery record and
syncs it to disk before the first deletion. Each ciphertext and checksum
removal is recorded separately. Afterward, a new versioned inventory must
show both target names absent and every protected version still present. The
two removals are separate operations, so partial failure is possible.

Review the preview and fixture manifest, then obtain explicit approval before
running `retention --apply`. If it reports a partial or uncertain result,
retain the recovery record under `GEOVIS_RETENTION_STATE_DIR`. An unfinished
record blocks unrelated apply operations for the same bucket and prefix. Retry
only the recorded pair using `retention --apply --recovery-file PATH` after
reviewing that file; retry rechecks scope, eligibility, versions, and protected
objects. A changed retention policy blocks retry, and even a completed record
is rechecked against a fresh versioned inventory before being reported as
complete again. Confirm both intended versions are absent and all retained
objects remain downloadable. Do not test deletion against production objects.
Bucket lifecycle rules may provide a second safety net, but they must not silently
conflict with the newest-three rule.

## Credential and key recovery

- Rotate a B2 key by creating a new key with the same exact bucket, prefix, and
  capabilities; update the protected environment file; run preflight,
  upload/download verification, alert, and restore checks; then revoke the old
  key. Recovery and Prime keys rotate independently.
- Recover the age identity from the offline secret-management copy directly
  onto the independent recovery host. Verify its expected public recipient
  locally before decrypting. If the identity is lost, existing ciphertext is
  unrecoverable; B2 credentials cannot replace it.
- To rotate age keys without losing old backups, add the new recipient for new
  sets while retaining the prior identities through the corresponding
  retention window. Re-encrypting old backups requires a controlled recovery
  environment with access to the old identity and must produce new verified B2
  objects before old objects are removed.

## Scheduling gate

After—and only after—the encrypted live replication, independently hosted
B2-only restore, acknowledged alert test, and lifecycle deletion test all pass:

```bash
sudo install -o root -g root -m 0644 deploy/systemd/geovis-offhost-backup.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/systemd/geovis-offhost-backup-alert.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/systemd/geovis-offhost-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geovis-offhost-backup.timer
systemctl list-timers geovis-offhost-backup.timer
```

The timer runs daily at 03:45 UTC with up to 30 minutes of jitter and catches up
after downtime. Do not enable it merely because repository tests pass. Do not
claim host-loss protection or close issue #5 until every live acceptance item
has durable evidence.
