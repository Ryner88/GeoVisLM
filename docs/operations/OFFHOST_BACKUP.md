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
6. An independent recovery host with Docker, the `postgis/postgis:16-3.4` and
   validated `geovis_lm_app:latest` images, this repository revision, `age`, B2
   CLI v4, `jq`, and enough scratch storage. It must not mount, copy, or read
   Prime's `/root/geovis-backups` directory.

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

```bash
export GEOVIS_RECOVERY_ENVIRONMENT=independent
sudo --preserve-env=GEOVIS_RECOVERY_ENVIRONMENT \
  /path/to/GeoVisLM/scripts/offhost_restore_drill.sh \
  --object-key geovislm/production/production-drill-YYYYMMDDTHHMMSSZ.tar.age \
  --identity-file /secure/secrets/geovis-offhost-age-identity.txt
```

The drill downloads ciphertext and its checksum directly from B2, verifies the
ciphertext, decrypts into a new recovery workspace, validates the source set,
and restores into uniquely named Docker volumes and network-isolated
containers. It compares the restored database and outputs to the embedded
production fingerprints, parses all restored metadata, checks relationships,
and repeats the isolated API/download verification. Scratch containers and
volumes are removed on exit. Preserve the root-only recovery evidence directory
until non-sensitive evidence has been reviewed and recorded.

The live acceptance record must identify the independent host without exposing
credentials, show that Prime's backup directory was neither mounted nor read,
and include the B2 object version/key, ciphertext digest, restore result,
coverage counts, alert receipt, and retention test result.

## Retention and deletion test

The client policy retains every verified set for 90 days and always retains the
newest three verified sets. Retention runs only after a new upload has passed
the download-and-checksum check. Preview candidates:

```bash
sudo systemd-run --wait --pipe \
  --property=EnvironmentFile=/etc/geovis-lm/offhost-backup.env \
  --working-directory=/opt/geovis_lm \
  /opt/geovis_lm/scripts/offhost_backup.py retention
```

For live acceptance, upload disposable encrypted fixture objects under a
dedicated test sub-prefix with timestamps that exercise the 90-day and
newest-three rules. Review the preview, run with `--apply`, and prove the
selected fixture ciphertext and sidecar were removed while retained objects
remain downloadable. Do not test deletion against production objects until the
preview has been reviewed. Bucket lifecycle rules may provide a second safety
net, but they must not silently conflict with the newest-three rule.

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
