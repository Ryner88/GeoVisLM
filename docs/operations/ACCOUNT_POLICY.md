# Production account policy

This policy applies to the GeoVisLM production service on Prime. Public account
registration is closed by default. Account records and credentials are private
operational data and must never be committed to Git or copied into tickets,
logs, or planning documents.

## Signup and invitations

- Production keeps `GEOVIS_SIGNUP_ENABLED=false`.
- `GEOVIS_SIGNUP_INVITE_CODE` is unset in production. An invite code does not
  override disabled signup.
- Open signup is prohibited until an approved abuse, email-verification, and
  account-recovery design is implemented.
- Invite-code signup is limited to staging or an explicitly approved,
  time-boxed enrollment window. Rotate the invite code and disable signup when
  that window closes.

## Roles and provisioning

Only an operator with Prime host access may provision an account. Give normal
users the `owner` role. Reserve `admin` for named operators who require
cross-project administration; do not use it as the default user role.

Run the offline command inside the dashboard container so it writes to the
persistent output volume while public signup remains disabled:

```bash
cd /opt/geovis_lm
docker compose exec dashboard python scripts/manage_users.py create \
  --email user@example.com --display-name "User Name" --role owner
```

The command prompts twice for the password and never prints or stores the
plaintext value. Confirm the account with a login/logout check through
Cloudflare, then confirm a known-invalid password is rejected. Do not record
either password.

## Recovery and access removal

Verify the requester's identity out of band before changing an account. For a
suspected compromise, deactivate first; deactivation rejects both new logins
and existing first-party sessions:

```bash
docker compose exec dashboard python scripts/manage_users.py deactivate --email user@example.com
docker compose exec dashboard python scripts/manage_users.py reset-password --email user@example.com
docker compose exec dashboard python scripts/manage_users.py activate --email user@example.com
```

For a confirmed session-secret compromise, replace `GEOVIS_SESSION_SECRET` in
the root-only `.env` and recreate the dashboard. This invalidates every browser
session, so announce the forced sign-in before rotation. Rotate
`GEOVIS_AUTH_TOKEN` separately if bearer access may also be compromised.

After recovery, verify the replacement password works, the previous password is
rejected, logout clears the session, and the account owns only the expected
projects. Keep an audit note with the operator, UTC time, account email, reason,
and checks performed, but no secrets.

## Review cadence

Review active production accounts and admin assignments quarterly and after any
operator departure. Deactivate unused accounts instead of deleting them so
project ownership and audit history remain intact.
