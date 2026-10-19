# Retention deletion preparation — 2026-10-18

This is a preparation record for issue #5. **No retention deletion was applied.**
The original dirty worktree was not changed.

## Policy and boundaries

- The policy keeps backup sets for 90 days and always keeps the newest three.
  A set qualifies for deletion only when its UTC timestamp is strictly older
  than the cutoff and it is outside the newest three.
- Selection is limited to direct children of the configured B2 prefix whose
  names match `production-drill-*.tar.age`. A ciphertext object must have a
  matching `.sha256` sidecar; an incomplete pair or future-dated name blocks
  the operation.
- The client verifies that a B2 key is restricted to the exact configured
  prefix and the required capabilities. The available production uploader key
  cannot be used to test deletion under a nested canary prefix.

## Prepared fixtures and verification

Local disposable fixtures:
`/home/samue/geovislm-recovery-data/retention-fixtures-20261018T202344Z`.
The manifest records the `as_of` time, object keys, checksums, and expected
delete/keep sets. These fixtures were **not uploaded to B2**.

| Scenario | Encrypted archive/checksum pairs | Expected deletion | Expected retained |
| --- | ---: | ---: | ---: |
| 90-day cutoff | 6 | 1 | 5 |
| Newest-three minimum | 4 | 1 | 3 |

All ten local ciphertext SHA-256 values matched their sidecars. Both scenario
selections matched the manifest at its recorded `as_of` time. One encrypted
archive decrypted with the recovery identity and contained only the harmless
`fixture.txt` payload. Deterministic unit tests also cover the exact 90-day
cutoff, incomplete pairs, future timestamps, nested prefixes, and preview
versus apply behavior with a mocked B2 client.

The full clean-checkout regression suite passed: **118 tests**. `git diff
--check` passed. A read-only production retention preview (without `--apply`)
returned `dry_run: true` and **zero candidates**; its private output is
`/home/samue/geovislm-recovery-data/retention-preview-20261018T202415Z.json`.

## Next controlled step

Obtain a B2 key restricted to the exact single canary prefix, with the backup
client's required capabilities. Upload and read back the ten direct-child
fixture pairs, inspect the live retention preview against the manifest, and
obtain explicit approval before `retention --apply`.
After an approved apply, verify only the selected ciphertext and sidecar were
deleted and every expected retained object remains downloadable. No production
backup object is a deletion-test target.

## Canary key check — 2026-10-18

The server-reported `namePrefix` for both available B2 keys is
`geovislm/production/`. The requested canary prefix is
`geovislm/production/retention-canary-20261018T202344Z/`. The reader key has
`listBuckets`, `listFiles`, and `readFiles`; the uploader key additionally has
`writeFiles` and `deleteFiles`. Neither key is restricted to the canary prefix,
so neither proves that access outside the canary is denied.

A canary-configured retention dry-run with the uploader key was rejected by
the client's exact-prefix preflight before it listed objects. The fixtures
remain local; **no canary upload, live canary preview, or deletion occurred**.
The prior read-only production preview found zero candidates, but it cannot
serve as the requested canary preview. A dedicated key with `namePrefix`
exactly equal to the canary prefix is needed before the live check can proceed.

For the requested single-prefix preview, ten new direct-child pairs were
prepared locally at
`/home/samue/geovislm-recovery-data/retention-fixtures-20261018T202344Z-single`.
Their exact prefix is
`geovislm/production/retention-canary-20261018T202344Z/`. The manifest
selects only `production-drill-20260719T204902Z.tar.age` for deletion and
keeps the other nine, including the newest three. All ten
ciphertext/sidecar checksums matched; one archive decrypted to a harmless
fixture file. Selection was checked at the manifest time and current time.
At this preparation stage, these pairs were still local; the live verification
below records their later upload.

After adding the single-prefix generator and regression test, the full clean
checkout suite passed again: **119 tests**. `git diff --check` passed.

## Live canary upload and dry-run — 2026-10-18

A newly supplied B2 key reported bucket restriction, exactly the canary
`namePrefix` above, and only `listBuckets`, `listFiles`, `readFiles`,
`writeFiles`, and `deleteFiles`. The credential file mode was `0600`. With this
key, B2 denied a download of an existing production checksum sidecar outside
the canary prefix; no outside-prefix data was written. The client's
exact-prefix preflight passed.

The canary prefix was empty before upload. All ten direct-child ciphertext
and checksum pairs were uploaded. The subsequent inventory contained exactly
the expected twenty objects. Every ciphertext and sidecar was downloaded and
its SHA-256 or sidecar content checked against the local manifest. The private
upload receipt is
`/home/samue/geovislm-recovery-data/retention-canary-upload-receipt-20261018.json`.

The live `retention` command ran **without `--apply`**. Its exact proposed
ciphertext deletion was:

```text
geovislm/production/retention-canary-20261018T202344Z/production-drill-20260719T204902Z.tar.age
```

If approved and applied later, its matching `.sha256` sidecar would be deleted
with it. The proposed key exactly matched the manifest's one expired pair.
The other nine pairs were excluded, including the newest three:

```text
production-drill-20260918T204902Z.tar.age
production-drill-20261016T204902Z.tar.age
production-drill-20261017T204902Z.tar.age
```

The only proposed key is under the canary prefix; no production key was
selected. A read-only post-preview inventory still contained all twenty
canary objects. The private preview record is
`/home/samue/geovislm-recovery-data/retention-canary-preview-20261018.json`.
**No deletion was performed.** Stop here for explicit approval before any
`retention --apply` operation.

## Deletion-path review — 2026-10-18

The current `--apply` code invokes `b2 rm` once for the selected ciphertext
and then once for its `.sha256` sidecar. B2's local CLI help says `rm` selects
the latest version by default; `--versions` is needed to select all versions.
A read-only version listing found exactly one version of each of the twenty
canary objects, including the proposed pair. Thus, if both `rm` calls succeed
against this unchanged inventory, they target both physical canary objects.
The dry-run did not delete either object.

The two removals are separate and are not atomic. A mocked failure on the
second call stopped `--apply`, but left the ciphertext absent and the sidecar
orphaned; the next retention preview then rejected the incomplete pair. This
is fail-closed for further retention, but it does not repair the partial
deletion. The current code has no post-delete version inventory or automatic
reconciliation. Do not treat a successful preview as proof that an eventual
apply removed both physical objects, and do not approve `--apply` until this
partial-failure behavior is acceptable or hardened.

## Recoverable deletion implementation — 2026-10-18

The preceding deletion-path review describes the former implementation. The
clean issue #5 checkout now ports the version-specific recovery flow from
commit `9e6f7e8` and fixes its nested-prefix and future-date regressions.
Normal production retention ignores objects under nested canary prefixes;
direct-child incomplete pairs, future-dated names, multiple versions, hide
markers, and unexpected objects still block deletion.

Immediately before each deletion, the code rechecks the B2 key's exact bucket
and prefix restrictions, lists versions, verifies the selected version IDs,
and recomputes the cutoff and newest-three decision. It syncs a private
recovery record before the first removal and after each component result.
The ciphertext and sidecar have separate command and final-inventory fields.
Afterward, a versioned inventory must show both target names absent and every
protected version present. A partial or uncertain result remains in a scoped
record; a normal apply for that scope is blocked until the explicit recovery
path is handled. Recovery skips components already proven absent and retains
the prior attempt result.

No live deletion was run as part of this fix.
The clean checkout's full regression suite passed: **125 tests**. With the
fixed code, a read-only production preview selected zero objects even while
the nested canary remained, and a read-only canary preview selected exactly
the manifest's one expired pair. A final versioned canary inventory still
contained all twenty expected physical objects.

## Failure-injection repair — 2026-10-18

The recovery path was exercised against an in-memory B2 inventory with
simulated interruptions after the first and second remote removals, an
unexpected final-listing I/O error, a B2 process error, and a record-sync
failure before the first removal. It also rejects a retry with a changed
retention policy and rechecks B2 before reporting a completed recovery record
as complete again. A recovered attempt removes only components still present
by the recorded version IDs; protected versions must remain. These tests did
not call live B2 deletion. The final test count and canary inventory check are
recorded after the clean checkout run.
The clean checkout's full suite passed **131 tests**, including the new
failure-injection cases. A subsequent read-only canary preview still proposed
only the manifest's expired pair, and `b2 ls --versions` showed all **20**
expected canary objects present with upload actions. No `b2 rm` was run live.

## Final read-only retention preflight — 2026-10-18

Using the repaired code and the exact canary-scoped key, the B2 dry-run again
selected only the expired canary ciphertext:

```text
geovislm/production/retention-canary-20261018T202344Z/production-drill-20260719T204902Z.tar.age
```

Its matching `.sha256` is the second physical object an approved apply would
remove. The versioned canary inventory contained exactly twenty unique upload
versions: those two proposed objects plus eighteen retained objects. All
twenty were downloaded by exact version ID, and their ciphertext SHA-256 or
sidecar content matched the local fixture manifest. A final listing found the
same twenty version IDs. The production-scoped read-only preview selected
zero objects, and the known genuine production recovery source was present.
The private preflight record is
`/home/samue/geovislm-recovery-data/final-retention-preflight-20261018.json`
(mode `0600`). **No deletion was performed.**

Recovery-record review is incomplete for the default
`/root/geovis-backups/offhost-retention-state` directory: the current operator
cannot read `/root`, and noninteractive `sudo` requires a password. No
pair-specific recovery records were found in accessible private or temporary
directories, and no `GEOVIS_RETENTION_STATE_DIR` is set in this session. A
privileged operator must inspect the configured state directory and confirm
there is no pending canary recovery record before approving `--apply`.
