# Secrets and Provider Security Plan

Status: planning. Implement provider integrations only with the phase that
needs them. Phase 1's selected USGS 3DEP and Geofabrik inputs require no API
key. OpenTopography, Census, FIRMS, Hugging Face, and hosted LLM credentials
are not Phase 1 prerequisites.

## Credential inventory

| Credential or identity | When needed | Handling |
| --- | --- | --- |
| Production backup B2 credentials, age material, alert webhook | Existing operations / Phase 0 verification | Follow `operations/OFFHOST_BACKUP.md`. Keep recovery identity separate from Prime. Verify host configuration without printing secrets. |
| OpenTopography API key | Only if its API is selected | Server-side secret; review its one-user/one-key and integration terms before enabling shared application use. |
| Census API key | Before production-scale population queries | Server-side secret. Census may put keys in query URLs; prevent URL, proxy, trace, and exception logging from recording them. |
| NWS application User-Agent and contact | Phase 5 | Configuration, not a secret. Use a stable app identifier and reachable contact. |
| FIRMS MAP_KEY | Phase 5 | Server-side secret. Redact query URLs and error messages; enforce provider limits. |
| USGS Water Data API key | Phase 5, if higher limits are needed | Server-side secret; prefer the documented `X-Api-Key` header to avoid query-string exposure. |
| Hosted model or Hugging Face token | Only for a later approved integration | Provider-specific secret with minimum scope; never required for Phase 1 exposure calculations. |

## Production controls

1. Keep credentials out of Git, browser bundles, generated reports, evidence
   manifests, and user-visible errors. Provision them through the existing
   protected host or deployment secret mechanism with restricted service
   access. Keep examples as names and placeholders only.
2. Give each provider its own credential and owner. Limit scope and quotas to
   the required operation; separate production, staging, and recovery access.
   Record rotation and revocation procedures without recording secret values.
3. Restrict outbound fetches to approved provider hosts and documented paths.
   Reject redirects to unapproved hosts, private/internal addresses, oversized
   responses, unsupported formats, and excessive geographic extents. Treat
   user-supplied URLs as untrusted input.
4. Set timeouts, bounded retries, concurrency and rate limits. Cache stable
   datasets by version and geography. Distinguish provider errors from missing
   geographic coverage; do not silently substitute a different source.
5. Log provider, endpoint class, status, timing, and request ID while redacting
   tokens, full credential-bearing URLs, location-sensitive query strings, and
   response bodies. Review any new telemetry destination before sending data.
6. Verify a provider's license, access rules, and permitted caching before
   production use. Store provenance and terms in `DATA_SOURCES.md` and in the
   versioned source record used by reports.

## Activation checks

For each provider, document its owner, approved hosts, data classification,
credential location, expected request volume, rate-limit behavior, retry
strategy, cache lifetime, terms, and fallback. Test key rotation and a denied
or expired credential path. Record a successful provider response using a
non-sensitive sample area before enabling user traffic.
