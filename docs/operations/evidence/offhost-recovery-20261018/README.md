# Issue #5: Independent B2 Recovery Drill, 2026-10-18

The recovery host repeated the isolated restore from the same encrypted B2
object, `geovislm/production/production-drill-20261003T154952Z.tar.age`, using
the prefix-scoped read-only recovery key. The source production commit was
`90c089bad3e2e9656b12d01b19f82dfac8c418e5`; the inspected application
image resolved to immutable ID
`sha256:3a0653e80f0293f12b91b2a03037df77d755e33404e4bd79439fc9d2cb9fc5f6`
with the matching revision label.

The first repeat, at `2026-10-18T20:07Z`, failed while fingerprinting
`public.spatial_ref_sys`. The saved psql stderr reported that PostgreSQL was
shutting down. Timestamped PostgreSQL logs show a fast shutdown request from
the PostGIS image's temporary initialization server at `20:07:37Z`. Docker
remained reachable, and the database container was still running when its
state was captured. Scratch cleanup was verified. This identified an early
`pg_isready` response during initialization, rather than a query error or a
Docker Desktop interruption. The drill was changed to require the PostGIS
initialization-complete log marker followed by `pg_isready`.

The second repeat, from `20:09:20Z` to `20:10:24Z`, passed. The full regression
suite passed before this repeat: **111 tests**. The `public.spatial_ref_sys`
query passed, and all recovery acceptance comparisons remained enabled:

| Check | Result |
| --- | --- |
| B2 ciphertext checksum and age decryption | Pass |
| Database fingerprint versus production | Match |
| Output manifest versus production | Match |
| Restored metadata references and relationships | 156 checked; none missing or orphaned |
| Isolated API | 6 projects, 6 runs, 36 artifact downloads, 470,202 bytes verified |
| Scratch containers and volumes | Both absent; cleanup verification passed |

The full private evidence bundle is at
`/home/samue/geovislm-recovery-data/drills/offhost-20261018T200920Z-17835`
on the recovery host. Files and directories are restricted to the recovery
operator. The preceding failed run's diagnostics are retained at
`/home/samue/geovislm-recovery-data/drills/offhost-20261018T200718Z-16372`.
The detailed fingerprints and manifests stay in those private directories.

| Private passing-run evidence | SHA-256 |
| --- | --- |
| `restored-db.tsv` | `6a0c618289ee5c3859db338ab90711216a426636e5aee35e900174bbd42bd5db` |
| `restored-outputs.tsv` | `271825f019708811fba196e8d9ce69c7a74d417970ee64bdd5de9ce91fbb694e` |
| `restored-api-validation.json` | `a8c21028e60750dc510432bd465c57d98ad0228719cabb575a7180bdc63af3d4` |
| `restored-content-validation.json` | `a140c7f7bd228da26ab0ff7f683b8a998b638dd8460f933270cd354cd4c684f3` |
| `scratch-cleanup.json` | `db1fd1f360cb23ea0363973b1b9537e72a72bba1b0298fb2ddffeea7561a8ead` |

The production database fingerprint and output manifest in the downloaded
backup have the same respective hashes as the restored files above. The alert
receipt and retention deletion tests remain separate issue #5 acceptance items.
