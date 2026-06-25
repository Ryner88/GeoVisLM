# GeoVisLM Security and Permission Controls

This document defines the operational security baseline for authentication,
authorization, project permissions, path traversal protection, and upload
safety. It is a specification only; implementation can follow after the project
and run model is in place.

## Goals

- Prevent unauthorized access to projects, runs, files, reports, and outputs.
- Keep uploaded files constrained to project/run storage directories.
- Make file ingestion safe by default.
- Define clear permission levels before collaboration features are implemented.
- Preserve a file-only local development path without weakening production rules.

## Authentication Requirements

Operational deployments must require authentication for all project, run, upload,
report, storage, and dashboard actions.

Required auth behavior:

- Anonymous users cannot create projects or runs.
- Anonymous users cannot upload files.
- Anonymous users cannot view project files or reports.
- API requests must identify a user or service account.
- Background workers must use service-account identity.
- Authentication events should be logged for operational audit.

Allowed unauthenticated routes:

- Health check endpoint
- Static public marketing or documentation pages, if added later
- Login or authentication callback endpoints

Recommended auth fields:

- `user_id`
- `email`
- `display_name`
- `role`
- `created_at`
- `last_login_at`
- `disabled_at`

## Project Permission Model

Project permissions are the primary authorization boundary.

Suggested roles:

- `owner`: full control over project, runs, files, reports, members, and deletion.
- `editor`: can create runs, upload files, retry failed runs, and generate reports.
- `viewer`: can view project metadata, runs, files, outputs, and reports.
- `commenter`: can view project reports and add comments when comments are implemented.
- `service`: background worker role scoped to operational updates.

Permission matrix:

| Action | Owner | Editor | Viewer | Commenter | Service |
| --- | --- | --- | --- | --- | --- |
| View project | yes | yes | yes | yes | scoped |
| Update project metadata | yes | yes | no | no | no |
| Archive/delete project | yes | no | no | no | no |
| Manage members | yes | no | no | no | no |
| Create run | yes | yes | no | no | no |
| Upload files | yes | yes | no | no | no |
| Run analysis | yes | yes | no | no | no |
| Retry/cancel run | yes | yes | no | no | scoped |
| View outputs | yes | yes | yes | yes | scoped |
| Generate reports | yes | yes | no | no | no |
| Add report comments | yes | yes | no | yes | no |
| Update run status | no | no | no | no | yes |

Rules:

- Every project must have exactly one owner at creation time.
- Ownership transfer must be explicit and audited.
- A user cannot access a run unless they can access the parent project.
- A user cannot access a file unless they can access the parent project.
- Cross-project file use is denied unless an explicit sharing mechanism is implemented.
- Service accounts must be scoped to worker actions only.

## API Authorization Rules

Every API handler should enforce permission checks before touching files or
running analysis.

Required checks:

- Resolve authenticated principal.
- Resolve project from route, run, or file metadata.
- Check permission for the requested action.
- Deny by default when project or permission is ambiguous.
- Return `403` for authenticated but unauthorized access.
- Return `404` when revealing resource existence would leak private project data.

Sensitive actions that require owner permission:

- Delete project
- Archive project
- Invite or remove members
- Change project visibility
- Transfer ownership
- Permanently delete files

## Path Traversal Rules

All file operations must stay inside the configured project/run storage root.

Forbidden path patterns:

- Absolute upload paths
- `..` segments
- Symlinks that resolve outside the storage root
- Backslash path traversal on platforms where it is meaningful
- Null bytes
- Control characters
- Hidden path components from uploaded filenames

Required path handling:

- Ignore client-provided directory components.
- Use `Path(filename).name` or equivalent basename extraction.
- Normalize filenames before writing.
- Resolve target path and verify it is inside the allowed root.
- Generate server-side storage names when possible.
- Never concatenate raw user input into filesystem paths.
- Never serve files directly by raw user-provided path.

Safe path check:

```text
storage_root = resolved project/run directory
target = resolved storage_root / safe_filename
allow only if target is relative to storage_root
```

## Upload Safety Policy

Uploads are untrusted until validation completes.

Required upload controls:

- Enforce file extension allowlist.
- Enforce single-file size limit.
- Enforce batch-size limit.
- Enforce maximum files per batch.
- Record SHA-256 checksum.
- Store original filename separately from stored filename.
- Write uploads to a quarantine or raw input folder before validation.
- Validate with format-specific parsers before analysis.
- Mark invalid files as unusable by workflows.
- Do not execute uploaded files.
- Do not import uploaded Python, shell, plugin, or macro code.

Rejected upload categories:

- Executable files
- Scripts
- Archives, until archive scanning exists
- Files with path traversal names
- Files with unsupported extensions
- Files that parser libraries cannot open
- Files exceeding configured limits

Recommended scanning:

- MIME sniffing as advisory metadata, not the sole trust mechanism
- Checksum tracking
- Optional antivirus or malware scanning before validation in production
- Optional archive scanning if compressed uploads are later supported

## Download and Static File Safety

Generated outputs should be served through authorized endpoints or scoped static
mounts.

Rules:

- Verify user can access parent project before serving file metadata.
- Do not expose arbitrary filesystem paths in download routes.
- Prefer file IDs over path parameters.
- Set safe content disposition filenames.
- Avoid rendering uploaded HTML/SVG inline unless sanitized.
- Serve reports and images as project-scoped outputs.

## Secrets and Configuration

Rules:

- Do not commit `.env`.
- Keep `.env.example` free of real credentials.
- Read secrets from environment variables in production.
- Never echo database URLs with passwords in logs.
- Mask credentials in error messages.
- Keep service account credentials separate from user credentials.

Relevant settings:

- `GEOVIS_DATABASE_URL`
- `GEOVIS_MAX_UPLOAD_FILE_MB`
- `GEOVIS_MAX_UPLOAD_BATCH_MB`
- `GEOVIS_MAX_BATCH_FILES`
- Future auth provider settings

## Audit and Logging

Security-sensitive events should be logged with user/service identity.

Events to log:

- Login and logout
- Failed auth attempts
- Project creation, archive, delete
- Member invite, role change, removal
- File upload, validation failure, deletion
- Run create, cancel, retry, failure
- Report generation
- Permission denial

Log fields:

- `event_type`
- `actor_id`
- `actor_type`
- `project_id`
- `run_id`
- `file_id`
- `ip_address`, when available
- `user_agent`, when available
- `created_at`
- `message`

## Local Development Mode

Local file-only mode may relax authentication for developer convenience, but it
must be explicit.

Rules:

- Development auth bypass must be controlled by a clearly named setting.
- Production defaults must require auth.
- Development mode should still enforce path traversal rules.
- Development mode should still enforce upload validation rules.
- Development mode should never be enabled implicitly in production.

Suggested setting:

```text
GEOVIS_DEV_AUTH_BYPASS=false
```

## Acceptance Criteria for Implementation

- All project, run, file, report, and output endpoints require an authenticated principal in production mode.
- Project permission checks are enforced before creating runs, uploading files, or viewing outputs.
- Owner, editor, viewer, commenter, and service roles are represented in the authorization layer.
- Upload paths are normalized and verified to stay inside the project/run storage root.
- Path traversal attempts are rejected with readable errors and no file writes.
- Unsupported and executable uploads are rejected before analysis.
- Upload size and batch limits are enforced.
- Files are not processed until validation succeeds.
- Secrets are loaded from environment variables and not logged.
- Security-sensitive events are auditable.
- Local development mode can run without full auth only when explicitly enabled.
