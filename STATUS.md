# GeoVisLM Project Status

Last reviewed: 2026-10-19

## Repository and operations

| Work | Repository status | Operational status |
| --- | --- | --- |
| Encrypted off-host backup | PR #12 was reverted by #13; the implementation was reapplied and fixed in [PR #14](https://github.com/Ryner88/GeoVisLM/pull/14) and [PR #15](https://github.com/Ryner88/GeoVisLM/pull/15). | [Issue #5](https://github.com/Ryner88/GeoVisLM/issues/5) remains open. The October 18 B2-only recovery drill passed. Alert receipt, retention deletion, current timer state, and continuing scheduled success still need verification. |
| Production deployment and GeoMiniLM approval boundary | [Issue #8](https://github.com/Ryner88/GeoVisLM/issues/8) closed | Its approval-boundary check passed on a prior deployment. Verify on Prime that the currently deployed commit matches current `main`; the October 18 backup came from `90c089b`. This does not approve the current GeoMiniLM model candidate. |
| Batch-upload improvements | [Issue #7](https://github.com/Ryner88/GeoVisLM/issues/7) closed; [PR #16](https://github.com/Ryner88/GeoVisLM/pull/16) merged | Verify configured quotas and recovery under load before claiming live readiness. |
| Collaboration notifications | [Issue #9](https://github.com/Ryner88/GeoVisLM/issues/9) closed; [PR #17](https://github.com/Ryner88/GeoVisLM/pull/17) merged | Repository work complete; live status has not been checked here. |

There is no GitHub issue #10 in this repository. The demo and portfolio work
remains an untracked future task in `docs/planning/FUTURE_TASKS.md`.

## Current work and AI planning

Complete Phase 0 verification: confirm Prime runs current `main`, inspect the
backup timer on the live host, finish issue #5 alert and retention acceptance,
and test upload quotas under load. The October 18 B2-only restore passed, but
its source commit was `90c089b`; it does not establish that current `main` is
deployed. The runbook requires production scheduling to remain disabled until
all live acceptance checks pass. No repository evidence confirms that the
timer has been enabled.

Next, establish the provider and licensing register, select bare-earth USGS
3DEP and Geofabrik OSM inputs for the first U.S. exposure milestone, and set
provider-security and provenance rules. `docs/DATA_SOURCES.md`,
`docs/SECRETS_AND_PROVIDER_SECURITY.md`, and `docs/DATA_PRIVACY.md` record
those planning requirements. OpenTopography, Census, FIRMS, Hugging Face, and
hosted LLM credentials are not prerequisites for the first milestone.

The AI phases are **Proposed / Not Started**, with no implementation dates or
GitHub issues assigned. Phase 1, evidence-grounded exposure analysis, is the
first AI development priority when implementation begins. See
`docs/planning/AI_ROADMAP.md` for scope and sequencing. Issues #7, #8, and #9
are closed repository work, not open AI development blockers.

The current GeoMiniLM candidate remains outside the production approval gate.
Its August 2026 sealed evaluation failed; see
`docs/GEOMINILM_PRODUCTION_ACCEPTANCE_2026-08-28.md` for the decision record.
The completed deployment and approval-boundary verification under issue #8
does not change that model result.

## Historical verification records

- The 2026-09-22 on-host production backup and isolated restore drill passed.
  Evidence: `docs/operations/evidence/production-drill-20260922/` and
  `docs/operations/BACKUP_RESTORE.md`.
- The 2026-10-03 Prime deployment and approval-boundary validation is recorded
  in issue #8. Its closure also records a 2026-10-17 service-health recheck.
- Off-host replication procedures and acceptance steps are documented in
  `docs/operations/OFFHOST_BACKUP.md`.
- The October 18 independent B2 restore passed against a backup sourced from
  `90c089b`. Its recorded regression run passed 111 tests. See
  `docs/operations/evidence/offhost-recovery-20261018/README.md`. This is a
  dated result, not a current test-suite count.

These are dated results. Consult the operational records for current service
and backup health.
