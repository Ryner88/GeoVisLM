from __future__ import annotations

import json
import secrets
import tempfile
import anyio
from html import escape
from urllib.parse import quote
from urllib.parse import parse_qs
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    DASHBOARD_SESSION_COOKIE,
    assert_project_access,
    copy_sample_dem_to_run,
    authenticate_user,
    create_dashboard_session,
    create_job_record,
    create_upload_batch,
    begin_batch_file_transfer,
    finish_batch_file_transfer,
    complete_upload_batch,
    cancel_upload_batch,
    cleanup_abandoned_uploads,
    batch_dir,
    get_upload_batch,
    ingest_file_paths,
    _ingest_file_paths_locked,
    project_upload_bytes,
    upload_error,
    create_project,
    create_report_comment,
    create_run_record,
    create_run_folders,
    create_user,
    ensure_storage,
    first_valid_dem,
    get_project,
    get_run,
    get_user_by_id,
    ingest_base64_files,
    get_job,
    get_report_comment,
    list_jobs,
    list_output_artifacts,
    invite_project_member,
    list_project_audit_events,
    list_report_comments,
    list_project_members,
    list_projects,
    list_runs,
    list_visible_runs,
    normalize_filename,
    normalize_workflow_type,
    resolve_workflow_template,
    mime_type_for_path,
    principal_from_request,
    project_upload_lock,
    public_user,
    moderate_report_comment,
    revoke_project_member,
    registered_output_path,
    run_dir,
    run_metadata_path,
    update_report_comment,
    update_run,
    utc_now,
    valid_vector_inputs,
    write_json,
)
from geovis_lm.dashboard.analysis_adapter import (
    AnalysisExecutionError,
    execute_dem_analysis,
    execute_flood_analysis,
    execute_wildfire_analysis,
)
from geovis_lm.dashboard.recommendations import recommend_workflow
from geovis_lm.reports.terrain_report import TerrainReportInputs, write_markdown_report


CONFIG = DashboardConfig.from_env()
ensure_storage(CONFIG)

app = FastAPI(title="GeoVisLM Dashboard", version="0.2.0")

BATCH_UPLOAD_SCRIPT = """
<script>
(() => {
  const form = document.querySelector('#batch-upload');
  if (!form) return;
  const picker = form.querySelector('input[type=file]');
  const button = form.querySelector('button');
  const progress = form.querySelector('progress');
  const message = form.querySelector('[role=status]');
  const results = form.querySelector('#upload-results');
  const cancelButton = form.querySelector('#cancel-upload');
  const base = form.dataset.api;
  const storageKey = `geovis-upload:${base}`;
  let active = null;
  try { active = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch { active = null; }
  const remember = (value) => {
    active = value;
    try {
      if (value) localStorage.setItem(storageKey, JSON.stringify(value));
      else localStorage.removeItem(storageKey);
    } catch { /* Uploads still work with in-memory state. */ }
    cancelButton.hidden = !value;
  };
  if (active) {
    cancelButton.hidden = false;
    message.textContent = 'An unfinished upload is available. Select the same files and submit to resume, or cancel it.';
  }
  const explain = (body) => body?.detail?.error_message || body?.error_message || 'Upload failed';
  const showOutcome = (outcome) => {
    remember(null);
    message.textContent = `Batch ${outcome.batch_status}. ${outcome.files.length} file(s) checked.`;
    for (const record of outcome.files) {
      const row = document.createElement('li');
      const errors = (record.validation_errors || []).map(error => error.error_message);
      const warnings = (record.warnings || []).map(warning => warning.message);
      row.textContent = `${record.original_filename}: ${record.status}${[...errors, ...warnings].length ? ' — ' + [...errors, ...warnings].join('; ') : ''}`;
      results.append(row);
    }
  };
  cancelButton.addEventListener('click', async () => {
    if (!active) return;
    cancelButton.disabled = true;
    try {
      if (!active.batchId) {
        const created = await fetch(base + '/batches', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({files: active.files, idempotency_key: active.idempotencyKey})
        });
        if (!created.ok) throw new Error(explain(await created.json()));
        active.batchId = (await created.json()).batch_id;
      }
      const response = await fetch(`${base}/batches/${active.batchId}`, {method: 'DELETE'});
      if (!response.ok && response.status !== 404) throw new Error(explain(await response.json()));
      remember(null);
      message.textContent = 'Upload canceled. Its staged files and unused quota were released.';
    } catch (error) {
      message.textContent = error.message;
    } finally {
      cancelButton.disabled = false;
    }
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const files = Array.from(picker.files);
    if (!files.length) return;
    button.disabled = true;
    progress.value = 0;
    results.replaceChildren();
    const total = files.reduce((sum, file) => sum + file.size, 0);
    const signature = JSON.stringify(files.map(file => [file.name, file.size]));
    if (files.length > Number(form.dataset.maxFiles) || files.some(file => file.size > Number(form.dataset.maxFile)) || total > Number(form.dataset.maxBatch)) {
      message.textContent = 'Selection exceeds a file, batch, or file count limit shown above.';
      button.disabled = false;
      return;
    }
    try {
      if (active && active.signature !== signature) {
        throw new Error('Select the same files to resume, or cancel the unfinished upload first.');
      }
      let batch;
      const resuming = Boolean(active && active.batchId);
      if (resuming) {
        message.textContent = 'Resuming upload…';
        const response = await fetch(`${base}/batches/${active.batchId}`);
        if (!response.ok) throw new Error(explain(await response.json()));
        batch = await response.json();
      } else {
        message.textContent = 'Creating upload batch…';
        if (!active) remember({batchId: null, signature, idempotencyKey: crypto.randomUUID(), files: files.map(file => ({filename: file.name, size_bytes: file.size, content_type: file.type || null}))});
        const created = await fetch(base + '/batches', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({files: active.files, idempotency_key: active.idempotencyKey})
        });
        batch = await created.json();
        if (!created.ok) throw new Error(explain(batch));
        remember({...active, batchId: batch.batch_id});
      }
      if (batch.status === 'completed') {
        showOutcome(batch.result);
        return;
      }
      if (batch.status === 'failed') throw new Error('This batch failed validation. Cancel it, then start a new upload.');
      let finished = 0;
      for (const [index, file] of files.entries()) {
        message.textContent = `Uploading ${file.name} (${index + 1}/${files.length})`;
        await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('PUT', `${base}/batches/${batch.batch_id}/files/${index}${resuming ? '?replace=true' : ''}`);
          xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) progress.value = total ? Math.round(100 * (finished + event.loaded) / total) : 100;
          };
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) resolve();
            else {
              let body;
              try { body = JSON.parse(xhr.responseText); } catch { body = {}; }
              reject(new Error(`${file.name}: ${explain(body)}`));
            }
          };
          xhr.onerror = () => reject(new Error(`${file.name}: network error`));
          xhr.send(file);
        });
        finished += file.size;
        progress.value = total ? Math.round(100 * finished / total) : 100;
      }
      message.textContent = 'Validating files…';
      const completed = await fetch(`${base}/batches/${batch.batch_id}/complete`, {method: 'POST'});
      const outcome = await completed.json();
      if (!completed.ok) throw new Error(explain(outcome));
      showOutcome(outcome);
    } catch (error) {
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
})();
</script>
"""


AUTH_PAGE_STYLE = """
      :root {
        color-scheme: dark;
        --bg: #020607;
        --panel: #101217;
        --panel-border: #1b2a31;
        --text: #f4f8ff;
        --muted: #7892b5;
        --border: #202832;
        --accent: #19d1b0;
        --accent-strong: #00f5d0;
        --danger: #fb7185;
        --success: #20c997;
      }
      * { box-sizing: border-box; }
      body {
        min-height: 100vh;
        margin: 0;
        padding: 0;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background:
          linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px),
          radial-gradient(circle at 50% 44%, rgba(13, 211, 170, .11), transparent 27rem),
          var(--bg);
        background-size: 50px 50px, 50px 50px, auto, auto;
        color: var(--text);
      }
      .auth-shell {
        min-height: 100vh;
        display: grid;
        grid-template-rows: auto 1fr auto;
        justify-items: center;
        padding: .35rem 1rem .85rem;
        overflow: auto;
      }
      .brand {
        display: grid;
        grid-template-columns: 42px auto;
        align-items: center;
        column-gap: .75rem;
        color: var(--text);
        line-height: 1;
      }
      .brand-mark {
        width: 42px;
        height: 42px;
        display: grid;
        place-items: center;
        border-radius: 14px;
        background: #19c3d3;
        color: #031115;
        box-shadow: 0 0 28px rgba(25, 195, 211, .22);
      }
      .brand-name { font-size: 1.1rem; font-weight: 800; }
      .brand-kicker {
        display: block;
        margin-top: .2rem;
        color: #9ab0cc;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: .7rem;
        letter-spacing: .18em;
      }
      main {
        align-self: center;
        width: min(100%, 35rem);
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-radius: 18px;
        padding: 2.55rem 2.55rem 2.45rem;
        box-shadow:
          0 0 0 1px rgba(7, 229, 197, .02),
          0 24px 70px rgba(0, 0, 0, .38),
          0 0 45px rgba(12, 211, 172, .09);
      }
      .eyebrow {
        display: flex;
        align-items: center;
        gap: .65rem;
        margin: 0 0 .75rem;
        color: var(--accent-strong);
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: .78rem;
        font-weight: 800;
        letter-spacing: .14em;
      }
      .eyebrow::before {
        content: "";
        width: .42rem;
        height: .42rem;
        border-radius: 999px;
        background: var(--accent);
      }
      h1 { margin: 0 0 .45rem; font-size: clamp(1.65rem, 4vw, 1.95rem); line-height: 1.15; letter-spacing: 0; }
      .lede { margin: 0 0 2rem; color: var(--muted); font-size: 1.08rem; line-height: 1.45; }
      form { display: grid; gap: 1rem; }
      label { display: grid; gap: .55rem; font-weight: 750; }
      input {
        width: 100%;
        min-height: 3.75rem;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: .78rem .95rem;
        font: inherit;
        background: #101217;
        color: var(--text);
      }
      input::placeholder { color: #7892b5; opacity: 1; }
      input:focus {
        border-color: rgba(25, 209, 176, .85);
        box-shadow: 0 0 0 3px rgba(25, 209, 176, .14);
        outline: none;
      }
      button {
        min-height: 3.75rem;
        border: 0;
        border-radius: 12px;
        padding: .65rem .9rem;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
      }
      .primary-action {
        margin-top: .25rem;
        background: linear-gradient(180deg, #22d1b5, #1fc9ac);
        color: #020607;
        font-size: 1rem;
      }
      .oauth-action {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1.35rem;
        background: transparent;
        color: var(--text);
        border: 1px solid var(--border);
        margin-bottom: .35rem;
      }
      .oauth-action svg { flex: 0 0 auto; }
      .or-divider {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        gap: 1rem;
        color: var(--muted);
        margin: .25rem 0 .55rem;
        font-size: .88rem;
      }
      .or-divider::before,
      .or-divider::after {
        content: "";
        height: 1px;
        background: var(--border);
      }
      .field-row { display: flex; align-items: center; justify-content: space-between; gap: .75rem; margin-bottom: -.35rem; }
      .field-row label { display: flex; align-items: center; gap: .45rem; font-weight: 500; color: var(--muted); }
      .field-row input[type="checkbox"] { width: 1rem; min-height: 1rem; }
      .password-field { position: relative; }
      .label-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
      .field-link { color: var(--accent-strong); font-size: .9rem; font-weight: 700; text-decoration: none; }
      .icon-field { position: relative; }
      .icon-field input { padding-left: 3.15rem; }
      .field-icon {
        position: absolute;
        left: 1rem;
        bottom: 1.08rem;
        color: #7c92b0;
        pointer-events: none;
      }
      .toggle-password {
        position: absolute;
        right: .35rem;
        bottom: .35rem;
        min-height: 1.95rem;
        width: auto;
        padding: .25rem .55rem;
        border: 1px solid var(--border);
        background: #141820;
        color: var(--text);
      }
      .hint { margin: -.25rem 0 0; color: var(--muted); font-size: .88rem; line-height: 1.35; }
      .feedback { display: none; margin: -.35rem 0 0; font-size: .88rem; line-height: 1.35; }
      .feedback.is-visible { display: block; }
      .feedback.error { color: var(--danger); }
      .feedback.ok { color: var(--success); }
      .alert {
        margin: 0 0 1rem;
        border: 1px solid rgba(251, 113, 133, .45);
        border-radius: 12px;
        padding: .75rem;
        background: rgba(251, 113, 133, .1);
        color: var(--danger);
      }
      .mode-switch {
        margin: 1.65rem 0 0;
        color: var(--muted);
        text-align: center;
      }
      a { color: var(--accent-strong); font-weight: 750; }
      @media (max-width: 520px) {
        .auth-shell { padding: .85rem 1rem 1.25rem; gap: 1.2rem; }
        .brand { grid-template-columns: 38px auto; }
        .brand-mark { width: 38px; height: 38px; border-radius: 12px; }
        main { width: 100%; align-self: center; }
        main { padding: 1.45rem; border-radius: 16px; }
        .lede { margin-bottom: 1.4rem; }
      }
"""


AUTH_PAGE_SCRIPT = """
    <script>
      const emailInput = document.querySelector("input[name='email']");
      const rememberInput = document.querySelector("input[name='remember_email']");
      const savedEmail = localStorage.getItem("geovis_login_email");
      if (emailInput && rememberInput && savedEmail) {
        emailInput.value = emailInput.value || savedEmail;
        rememberInput.checked = true;
      }

      document.querySelectorAll("[data-password-field]").forEach((field) => {
        const input = field.querySelector("input");
        const toggle = field.querySelector("[data-toggle-password]");
        const caps = document.querySelector(`[data-caps-for="${input.id}"]`);
        if (toggle) {
          toggle.addEventListener("click", () => {
            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            toggle.textContent = showing ? "Show" : "Hide";
            toggle.setAttribute("aria-pressed", String(!showing));
          });
        }
        if (caps) {
          input.addEventListener("keyup", (event) => {
            const active = event.getModifierState && event.getModifierState("CapsLock");
            caps.classList.toggle("is-visible", active);
          });
          input.addEventListener("blur", () => caps.classList.remove("is-visible"));
        }
      });

      document.querySelectorAll("[data-validate]").forEach((input) => {
        const feedback = document.querySelector(`[data-feedback-for="${input.id}"]`);
        if (!feedback) return;
        input.addEventListener("blur", () => {
          const valid = input.checkValidity();
          feedback.classList.toggle("is-visible", !valid);
          feedback.classList.toggle("error", !valid);
        });
      });

      document.querySelector("form")?.addEventListener("submit", () => {
        if (!emailInput || !rememberInput) return;
        if (rememberInput.checked) {
          localStorage.setItem("geovis_login_email", emailInput.value);
        } else {
          localStorage.removeItem("geovis_login_email");
        }
      });
    </script>
"""


BRAND_MARKUP = """
    <header class="brand" aria-label="GeoVisLM">
      <span class="brand-mark" aria-hidden="true">
        <svg width="23" height="23" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="8.4" stroke="currentColor" stroke-width="2"/>
          <path d="M3.6 12h16.8M12 3.6c2.25 2.22 3.38 5.02 3.38 8.4s-1.13 6.18-3.38 8.4M12 3.6C9.75 5.82 8.62 8.62 8.62 12s1.13 6.18 3.38 8.4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </span>
      <span>
        <span class="brand-name">GeoVisLM</span>
        <span class="brand-kicker">AI GEOSPATIAL LAB</span>
      </span>
    </header>
"""


GOOGLE_ICON = """
          <svg width="19" height="19" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#4285F4" d="M21.6 12.23c0-.76-.07-1.49-.19-2.19H12v4.14h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.89-1.74 2.98-4.3 2.98-7.48z"/>
            <path fill="#34A853" d="M12 22c2.7 0 4.96-.89 6.62-2.42l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.81-1.76-5.6-4.12H3.06v2.6A10 10 0 0 0 12 22z"/>
            <path fill="#FBBC05" d="M6.4 13.91A6.02 6.02 0 0 1 6.08 12c0-.66.11-1.31.32-1.91v-2.6H3.06A10 10 0 0 0 2 12c0 1.61.39 3.13 1.06 4.51l3.34-2.6z"/>
            <path fill="#EA4335" d="M12 5.97c1.47 0 2.78.5 3.82 1.49l2.87-2.87C16.95 2.97 14.69 2 12 2a10 10 0 0 0-8.94 5.49l3.34 2.6C7.19 7.73 9.4 5.97 12 5.97z"/>
          </svg>
"""


EMAIL_ICON = """
          <svg class="field-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4.5 6.8h15v10.4h-15z" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>
            <path d="m5.2 7.5 6.8 5 6.8-5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
"""


LOCK_ICON = """
          <svg class="field-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M7 10.5V8.2a5 5 0 0 1 10 0v2.3" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
            <path d="M6 10.5h12v9H6z" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>
          </svg>
"""


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if (
        exc.status_code == 401
        and not request.url.path.startswith(("/api", "/healthz", "/readyz", "/outputs", "/login"))
        and request.method in {"GET", "POST"}
    ):
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


class ProjectCreate(BaseModel):
    name: str = Field(default="Untitled Project", min_length=1, max_length=120)
    description: str = ""


class ProjectInvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = "viewer"


class ReportCommentCreate(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=10000)


class ReportCommentUpdate(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=10000)


class RunCreate(BaseModel):
    name: str | None = None
    workflow_type: str = "terrain"
    parameters: dict = Field(default_factory=dict)


class UploadFilePayload(BaseModel):
    filename: str
    content_b64: str
    content_type: str | None = None


class BatchUploadPayload(BaseModel):
    files: list[UploadFilePayload]


class StagedFilePayload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    content_type: str | None = Field(default=None, max_length=255)


class StagedBatchPayload(BaseModel):
    files: list[StagedFilePayload] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)


class SignupPayload(BaseModel):
    email: str
    password: str = Field(min_length=12)
    display_name: str = ""
    invite_code: str | None = None


class LoginPayload(BaseModel):
    email: str
    password: str


def set_session_cookie(response: RedirectResponse | JSONResponse, user: dict) -> None:
    session = create_dashboard_session(CONFIG, user["id"], user.get("role", "owner"))
    response.set_cookie(
        DASHBOARD_SESSION_COOKIE,
        session,
        httponly=True,
        secure=CONFIG.session_cookie_secure,
        samesite="lax",
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/") -> str:
    error = request.query_params.get("error")
    escaped_next = escape(next)
    encoded_next = escape(quote(next, safe="/"))
    error_markup = "<div class='alert' role='alert'>Invalid email or password.</div>" if error else ""
    signup_link = (
        f"<p class='mode-switch'>Don't have an account? <a href='/signup?next={encoded_next}'>Create one</a></p>"
        if CONFIG.signup_enabled
        else ""
    )
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign in to GeoVisLM</title>
    <style>
{AUTH_PAGE_STYLE}
    </style>
  </head>
  <body>
    <div class="auth-shell">
{BRAND_MARKUP}
      <main aria-labelledby="auth-title">
        <p class="eyebrow">SESSION AUTH</p>
        <h1 id="auth-title">Welcome back</h1>
        <p class="lede">Log in to your account</p>
        {error_markup}
        <form method="post" action="/login" novalidate>
          <input type="hidden" name="next" value="{escaped_next}">
          <button class="oauth-action" type="button">{GOOGLE_ICON}<span>Continue with Google</span></button>
          <div class="or-divider">OR</div>

          <label class="icon-field" for="email">Email
            {EMAIL_ICON}
            <input id="email" name="email" type="email" autocomplete="email" inputmode="email" placeholder="you@example.com" required autofocus data-validate>
          </label>
          <p class="feedback error" data-feedback-for="email">Enter a valid email address.</p>

          <div class="password-field icon-field" data-password-field>
            <div class="label-row">
              <label for="password">Password</label>
              <a class="field-link" href="/login?next={encoded_next}">Forgot password?</a>
            </div>
            {LOCK_ICON}
            <input id="password" name="password" type="password" autocomplete="current-password" placeholder="........" required data-validate>
          </div>
          <p class="feedback error" data-feedback-for="password">Enter your password.</p>
          <p class="feedback error" data-caps-for="password">Caps Lock is on.</p>

          <input id="remember-email" name="remember_email" type="checkbox" value="1" hidden>
          <button class="primary-action" type="submit">Log in</button>
        </form>
        {signup_link}
      </main>
      <span aria-hidden="true"></span>
    </div>
{AUTH_PAGE_SCRIPT}
  </body>
</html>
"""


@app.post("/login")
async def login(request: Request) -> RedirectResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    next_url = form.get("next", ["/"])[0] or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    token = form.get("token", [""])[0]
    if token:
        if not CONFIG.auth_token or not secrets.compare_digest(token, CONFIG.auth_token):
            return RedirectResponse(f"/login?error=1&next={quote(next_url, safe='/')}", status_code=303)
        session_user = {
            "id": form.get("user_id", ["dashboard-user"])[0] or "dashboard-user",
            "role": form.get("role", ["owner"])[0] or "owner",
        }
        response = RedirectResponse(next_url, status_code=303)
        set_session_cookie(response, session_user)
        return response

    try:
        user = authenticate_user(CONFIG, form.get("email", [""])[0], form.get("password", [""])[0])
    except HTTPException:
        return RedirectResponse(f"/login?error=1&next={quote(next_url, safe='/')}", status_code=303)
    response = RedirectResponse(next_url, status_code=303)
    set_session_cookie(response, user)
    return response


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, next: str = "/") -> str:
    if not CONFIG.signup_enabled:
        raise HTTPException(status_code=404, detail="Signup is disabled")
    error = request.query_params.get("error")
    escaped_next = escape(next)
    encoded_next = escape(quote(next, safe="/"))
    invite_field = (
        f"""
        <div class="password-field icon-field" data-password-field>
          <label for="invite-code">Invite code</label>
          {LOCK_ICON}
          <input id="invite-code" name="invite_code" type="password" autocomplete="one-time-code" placeholder="........" required data-validate>
        </div>
        <p class="feedback error" data-feedback-for="invite-code">Enter your invite code.</p>
        <p class="feedback error" data-caps-for="invite-code">Caps Lock is on.</p>
"""
        if CONFIG.signup_invite_code
        else ""
    )
    error_markup = f"<div class='alert' role='alert'>{escape(error)}</div>" if error else ""
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Create a GeoVisLM account</title>
    <style>
{AUTH_PAGE_STYLE}
    </style>
  </head>
  <body>
    <div class="auth-shell">
{BRAND_MARKUP}
      <main aria-labelledby="auth-title">
        <p class="eyebrow">SESSION AUTH</p>
        <h1 id="auth-title">Create your account</h1>
        <p class="lede">Sign up to get started</p>
        {error_markup}
        <form method="post" action="/signup" novalidate>
          <input type="hidden" name="next" value="{escaped_next}">
          <button class="oauth-action" type="button">{GOOGLE_ICON}<span>Continue with Google</span></button>
          <div class="or-divider">OR</div>

          <label class="icon-field" for="signup-email">Email
            {EMAIL_ICON}
            <input id="signup-email" name="email" type="email" autocomplete="email" inputmode="email" placeholder="you@example.com" required autofocus data-validate>
          </label>
          <p class="feedback error" data-feedback-for="signup-email">Enter a valid email address.</p>

          <input id="display-name" name="display_name" autocomplete="name" hidden>

          <div class="password-field icon-field" data-password-field>
            <label for="signup-password">Password</label>
            {LOCK_ICON}
            <input id="signup-password" name="password" type="password" autocomplete="new-password" minlength="12" placeholder="........" required data-validate>
          </div>
          <p class="feedback error" data-feedback-for="signup-password">Use at least 12 characters.</p>
          <p class="feedback error" data-caps-for="signup-password">Caps Lock is on.</p>

          <div class="password-field icon-field" data-password-field>
            <label for="confirm-password">Confirm Password</label>
            {LOCK_ICON}
            <input id="confirm-password" name="confirm_password" type="password" autocomplete="new-password" minlength="12" placeholder="........" required data-validate>
          </div>
          <p class="feedback error" data-feedback-for="confirm-password">Confirm your password.</p>
          <p class="feedback error" data-caps-for="confirm-password">Caps Lock is on.</p>

          {invite_field}
          <input id="remember-signup-email" name="remember_email" type="checkbox" value="1" hidden>
          <button class="primary-action" type="submit">Create account</button>
        </form>
        <p class="mode-switch">Already have an account? <a href="/login?next={encoded_next}">Sign in</a></p>
      </main>
      <span aria-hidden="true"></span>
    </div>
{AUTH_PAGE_SCRIPT}
  </body>
</html>
"""


@app.post("/signup")
async def signup(request: Request) -> RedirectResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    next_url = form.get("next", ["/"])[0] or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    if form.get("confirm_password", [form.get("password", [""])[0]])[0] != form.get("password", [""])[0]:
        return RedirectResponse(
            f"/signup?error={quote('Passwords do not match')}&next={quote(next_url, safe='/')}",
            status_code=303,
        )
    try:
        user = create_user(
            CONFIG,
            form.get("email", [""])[0],
            form.get("password", [""])[0],
            display_name=form.get("display_name", [""])[0],
            invite_code=form.get("invite_code", [""])[0],
        )
    except HTTPException as exc:
        return RedirectResponse(
            f"/signup?error={quote(str(exc.detail))}&next={quote(next_url, safe='/')}",
            status_code=303,
        )
    response = RedirectResponse(next_url, status_code=303)
    set_session_cookie(response, user)
    return response


@app.post("/api/auth/signup")
def signup_api(payload: SignupPayload) -> JSONResponse:
    user = create_user(
        CONFIG,
        payload.email,
        payload.password,
        display_name=payload.display_name,
        invite_code=payload.invite_code,
    )
    response = JSONResponse({"user": public_user(user)})
    set_session_cookie(response, user)
    return response


@app.post("/api/auth/login")
def login_api(payload: LoginPayload) -> JSONResponse:
    user = authenticate_user(CONFIG, payload.email, payload.password)
    response = JSONResponse({"user": public_user(user)})
    set_session_cookie(response, user)
    return response


@app.get("/api/auth/me")
def me_api(request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    user = get_user_by_id(CONFIG, principal["user_id"])
    return {"user": public_user(user) if user else principal}


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(
        DASHBOARD_SESSION_COOKIE,
        httponly=True,
        secure=CONFIG.session_cookie_secure,
        samesite="lax",
    )
    return response


def project_for_run(run: dict) -> dict:
    return get_project(CONFIG, run["project_id"])


def finish_analysis_status(run_id: str, **updates) -> dict:
    initial = get_run(CONFIG, run_id)
    with project_upload_lock(CONFIG, initial["project_id"]):
        current = get_run(CONFIG, run_id)
        if current["status"] != "running":
            return current
        return update_run(CONFIG, run_id, **updates)


def run_analysis_workflow(run_id: str, *, from_worker: bool = False) -> dict:
  initial = get_run(CONFIG, run_id)
  with project_upload_lock(CONFIG, initial["project_id"]):
    metadata = get_run(CONFIG, run_id)
    if from_worker:
      if metadata["status"] != "queued":
        raise upload_error("run_not_ready", "Queued job cannot start from this state")
    else:
      if metadata["status"] == "queued":
        raise upload_error("run_not_ready", "Use the queued job to run this analysis")
      if metadata["status"] not in {"created", "uploaded", "retrying"}:
        raise upload_error("run_not_ready", "Analysis cannot start from this state")
    metadata = update_run(CONFIG, run_id, status="running", status_message="Analysis started")
  workflow_type = normalize_workflow_type(metadata.get("workflow_type", "terrain"))
  template = resolve_workflow_template(workflow_type)

  recommendation = metadata.get("recommendation")
  if recommendation and recommendation.get("status") != "approved":
    return finish_analysis_status(
      run_id,
      workflow_type=workflow_type,
      status="failed",
      status_message="Recommendation approval required",
      error_code="recommendation_not_approved",
      error_message="Approve the GeoMiniLM recommendation before execution",
      retryable=False,
    )

  dem_path = first_valid_dem(metadata)
  if not dem_path or not dem_path.exists():
    return finish_analysis_status(
      run_id,
      workflow_type=workflow_type,
      status="failed",
      status_message="No valid DEM input found",
      error_code="missing_dem",
      error_message="Upload a valid DEM before analysis",
      retryable=True,
    )

  missing_crs_inputs = [
    item.get("stored_filename") or item.get("original_filename") or "Shapefile"
    for item in metadata.get("inputs", [])
    if item.get("status") == "valid"
    and item.get("extension") == ".shp"
    and not item.get("metadata", {}).get("crs")
  ]
  if missing_crs_inputs:
    return finish_analysis_status(
      run_id,
      workflow_type=workflow_type,
      status="failed",
      status_message="Shapefile CRS is missing",
      error_code="missing_crs",
      error_message=f"Upload a .prj with {', '.join(missing_crs_inputs)} in a new analysis before running this workflow",
      retryable=False,
    )

  workflow_labels = {
    "terrain": "Terrain analysis",
    "flood_risk": "Flood risk analysis",
    "wildfire_risk": "Wildfire risk analysis",
  }
  workflow_label = workflow_labels.get(workflow_type, "Terrain analysis")
  try:
    vector_paths = valid_vector_inputs(metadata)
    if workflow_type == "flood_risk":
      result = execute_flood_analysis(
        dem_path,
        maps_dir=run_dir(CONFIG, run_id) / "maps",
        reports_dir=run_dir(CONFIG, run_id) / "reports",
        vector_paths=vector_paths,
        parameters=metadata.get("parameters", {}),
      )
    elif workflow_type == "wildfire_risk":
      result = execute_wildfire_analysis(
        dem_path,
        maps_dir=run_dir(CONFIG, run_id) / "maps",
        reports_dir=run_dir(CONFIG, run_id) / "reports",
        vector_paths=vector_paths,
        parameters=metadata.get("parameters", {}),
      )
    else:
      result = execute_dem_analysis(
        dem_path,
        maps_dir=run_dir(CONFIG, run_id) / "maps",
        reports_dir=run_dir(CONFIG, run_id) / "reports",
        vectors_dir=run_dir(CONFIG, run_id) / "vectors",
        renders_dir=run_dir(CONFIG, run_id) / "renders",
        vector_paths=vector_paths,
        parameters=metadata.get("parameters", {}),
      )
  except AnalysisExecutionError as exc:
    return finish_analysis_status(
      run_id,
      workflow_type=workflow_type,
      status="failed",
      status_message=f"{workflow_label} failed",
      error_code=exc.error_code,
      error_message=exc.error_message,
      error_detail=json.dumps(exc.as_detail(), sort_keys=True),
      retryable=exc.retryable,
    )
  except Exception as exc:
    return finish_analysis_status(
      run_id,
      workflow_type=workflow_type,
      status="failed",
      status_message=f"{workflow_label} failed",
      error_code="dem_analysis_failed",
      error_message=str(exc),
      error_detail=repr(exc),
      retryable=True,
    )

  result = finish_analysis_status(
    run_id,
    workflow_type=workflow_type,
    status="completed",
    status_message=f"{workflow_label} completed",
    outputs=result.outputs,
    crs=result.metadata.get("crs"),
    execution_adapter=result.adapter,
    execution_metadata=result.metadata,
    retryable=False,
    error_code=None,
    error_message=None,
    error_detail=None,
  )
  result["template_id"] = template["template_id"]
  result["template_version"] = template["template_version"]
  result["template"] = template
  return result


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict:
    storage_ready = CONFIG.output_root.exists() and CONFIG.output_root.is_dir()
    return {
        "status": "ready" if storage_ready else "not_ready",
        "storage": storage_ready,
        "database_mode": bool(CONFIG.database_url),
        "auth_required": CONFIG.require_auth,
        "auth_configured": bool(CONFIG.effective_session_secret) if CONFIG.require_auth else True,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> str:
    principal = principal_from_request(request, CONFIG)
    projects = list_projects(CONFIG, principal)
    projects_by_id = {project["id"]: project for project in projects}
    runs = list_visible_runs(CONFIG, principal)
    project_items = "\n".join(
        f"<li><a href='/projects/{project['id']}'>{project['name']}</a> <code>{project['status']}</code></li>"
        for project in projects
    ) or "<li>No projects yet</li>"
    run_items = "\n".join(
        f"<li><a href='/runs/{run['run_id']}'>{escape(run['name'])}</a> "
        f"<code>{escape(run['status'])}</code> "
        f"<a href='/projects/{run['project_id']}'>{escape(projects_by_id[run['project_id']]['name'])}</a></li>"
        for run in runs[:20]
    ) or "<li>No runs yet</li>"
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>GeoVisLM Dashboard</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 1100px; }}
      main {{ display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
      form, section {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; }}
      input, textarea, button {{ font: inherit; margin: .25rem 0; width: 100%; box-sizing: border-box; }}
      code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; }}
    </style>
  </head>
  <body>
    <h1>GeoVisLM Dashboard</h1>
    <main>
      <form method="post" action="/dashboard/projects">
        <h2>New Project</h2>
        <input name="name" placeholder="Project name" required>
        <textarea name="description" placeholder="Description"></textarea>
        <button>Create project</button>
      </form>
      <section>
        <h2>Projects</h2>
        <ul>{project_items}</ul>
      </section>
      <section>
        <h2>Recent Runs</h2>
        <ul>{run_items}</ul>
      </section>
    </main>
  </body>
</html>
"""


@app.post("/api/projects")
def create_project_api(payload: ProjectCreate, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    return create_project(CONFIG, payload.name, principal["user_id"], payload.description)


@app.get("/api/projects")
def list_projects_api(request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    return {"projects": list_projects(CONFIG, principal)}


@app.get("/api/projects/{project_id}")
def get_project_api(project_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "view")
    return project


@app.get("/api/projects/{project_id}/members")
def list_project_members_api(project_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    return list_project_members(CONFIG, project, principal)


@app.post("/api/projects/{project_id}/invitations")
def invite_project_member_api(project_id: str, payload: ProjectInvitationCreate, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    return invite_project_member(CONFIG, project, principal, payload.email, payload.role)


@app.delete("/api/projects/{project_id}/members/{user_id}")
def revoke_project_member_api(project_id: str, user_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    return revoke_project_member(CONFIG, project, principal, user_id)


@app.get("/api/projects/{project_id}/audit-events")
def list_project_audit_events_api(project_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "manage_members")
    return {"project_id": project_id, "events": list_project_audit_events(CONFIG, project_id)}


@app.post("/api/projects/{project_id}/runs")
def create_project_run(project_id: str, payload: RunCreate, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "create_run")
    return create_run_record(
        CONFIG,
        project,
        principal["user_id"],
        workflow_type=payload.workflow_type,
        name=payload.name,
        parameters=payload.parameters,
    )


@app.get("/api/projects/{project_id}/runs")
def list_project_runs(project_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "view")
    return {"project_id": project_id, "runs": list_runs(CONFIG, project_id)}


@app.post("/api/projects/{project_id}/runs/{run_id}/files")
async def upload_project_run_files(project_id: str, run_id: str, request: Request) -> dict:
    run = authorized_upload_run(project_id, run_id, request)
    limit = min(CONFIG.max_upload_batch_bytes * 2, 16 * 1024 * 1024)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise upload_error("legacy_upload_too_large", "Use staged uploads for JSON requests over 16 MB", status=413)
        body.extend(chunk)
    try:
        payload = BatchUploadPayload.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]) from exc
    return await run_in_threadpool(ingest_base64_files, CONFIG, run, [item.model_dump() for item in payload.files])


@app.post("/api/projects/{project_id}/runs/{run_id}/files/multipart")
async def upload_project_run_multipart(project_id: str, run_id: str, request: Request) -> dict:
    run = authorized_upload_run(project_id, run_id, request)
    # Bound parsing by the batch limit. The project quota is checked under the
    # upload lock after the request body has been fully spooled.
    return await _upload_project_run_multipart(request, run, CONFIG.max_upload_batch_bytes + 1024 * 1024)


async def _upload_project_run_multipart(request: Request, run: dict, wire_limit: int) -> dict:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise upload_error("invalid_upload", "Content-Length must be an integer") from exc
        if declared_length > wire_limit:
            raise upload_error("batch_too_large", f"Batch exceeds the {CONFIG.max_upload_batch_bytes} byte limit", status=413)
    received = 0

    async def bounded_receive():
        nonlocal received
        message = await request.receive()
        received += len(message.get("body", b""))
        if received > wire_limit:
            raise upload_error("batch_too_large", f"Batch exceeds the {CONFIG.max_upload_batch_bytes} byte limit", status=413)
        return message

    limited_request = Request(request.scope, receive=bounded_receive)
    async with limited_request.form(max_files=CONFIG.max_batch_files + 1) as form:
        uploads = form.getlist("files")
        if not uploads or len(uploads) > CONFIG.max_batch_files or any(not isinstance(item, UploadFile) for item in uploads):
            raise upload_error("invalid_upload", f"Send 1 to {CONFIG.max_batch_files} file parts named files")
        with tempfile.TemporaryDirectory(dir=run_dir(CONFIG, run["run_id"])) as temporary:
            paths = []
            total_size = 0
            for index, upload in enumerate(uploads):
                name = normalize_filename(upload.filename or "")
                if upload.size is not None and upload.size > CONFIG.max_upload_file_bytes:
                    raise upload_error("file_too_large", f"{name} exceeds the {CONFIG.max_upload_file_bytes} byte file limit", name, 413)
                destination = Path(temporary) / str(index)
                size = 0
                async with await anyio.open_file(destination, "wb") as handle:
                    while chunk := await upload.read(1024 * 1024):
                        size += len(chunk)
                        total_size += len(chunk)
                        if size > CONFIG.max_upload_file_bytes:
                            raise upload_error("file_too_large", f"{name} exceeds the {CONFIG.max_upload_file_bytes} byte file limit", name, 413)
                        if total_size > CONFIG.max_upload_batch_bytes:
                            raise upload_error("batch_too_large", f"Batch exceeds the {CONFIG.max_upload_batch_bytes} byte limit", status=413)
                        await handle.write(chunk)
                paths.append((upload.filename or name, destination, upload.content_type))
            return await run_in_threadpool(_ingest_multipart_paths_with_lock, run, paths, total_size)


def _ingest_multipart_paths_with_lock(run: dict, paths: list, total_size: int) -> dict:
    project_id = run["project_id"]
    with project_upload_lock(CONFIG, project_id):
        current_run = get_run(CONFIG, run["run_id"])
        if current_run["status"] not in {"created", "uploaded", "retrying"}:
            raise upload_error("run_not_editable", "Uploads are closed for this analysis")
        remaining = max(0, CONFIG.max_project_bytes - project_upload_bytes(CONFIG, project_id))
        if total_size > remaining:
            raise upload_error("project_quota_exceeded", "Upload exceeds the remaining project storage quota", status=413)
        return _ingest_file_paths_locked(CONFIG, current_run, paths)


def authorized_upload_run(project_id: str, run_id: str, request: Request, *, require_editable: bool = True) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "upload")
    run = get_run(CONFIG, run_id)
    if run["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if require_editable and run["status"] not in {"created", "uploaded", "retrying"}:
        raise upload_error("run_not_editable", "Uploads are closed for this analysis")
    return run


@app.post("/api/projects/{project_id}/runs/{run_id}/batches")
async def begin_upload_batch(project_id: str, run_id: str, request: Request) -> dict:
    run = authorized_upload_run(project_id, run_id, request)
    payload = await _read_staged_batch_payload(request)
    if len(payload.files) > CONFIG.max_batch_files:
        raise upload_error("too_many_files", f"Select 1 to {CONFIG.max_batch_files} files", status=413)
    return await run_in_threadpool(
        _cleanup_and_create_upload_batch,
        project_id,
        run,
        [item.model_dump() for item in payload.files],
        payload.idempotency_key,
    )


def _cleanup_and_create_upload_batch(project_id: str, run: dict, files: list[dict], idempotency_key: str | None) -> dict:
    cleanup_abandoned_uploads(CONFIG, project_id)
    return create_upload_batch(CONFIG, run, files, idempotency_key=idempotency_key)


async def _read_staged_batch_payload(request: Request) -> StagedBatchPayload:
    limit = 64 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise upload_error("invalid_upload", "Content-Length must be an integer") from exc
        if declared_length > limit:
            raise upload_error("batch_metadata_too_large", "Staged batch metadata exceeds 64 KiB", status=413)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise upload_error("batch_metadata_too_large", "Staged batch metadata exceeds 64 KiB", status=413)
        body.extend(chunk)
    try:
        return StagedBatchPayload.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()],
        ) from exc


@app.get("/api/projects/{project_id}/runs/{run_id}/batches/{batch_id}")
def upload_batch_status(project_id: str, run_id: str, batch_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "view")
    run = get_run(CONFIG, run_id)
    if run["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return get_upload_batch(CONFIG, run_id, batch_id)


@app.put("/api/projects/{project_id}/runs/{run_id}/batches/{batch_id}/files/{file_index}")
async def stage_upload_file(project_id: str, run_id: str, batch_id: str, file_index: int, request: Request, replace: bool = False) -> dict:
    authorized_upload_run(project_id, run_id, request)
    item = await run_in_threadpool(begin_batch_file_transfer, CONFIG, project_id, run_id, batch_id, file_index, replace_uploaded=replace)
    if item["status"] == "uploaded":
        return {"batch_id": batch_id, "filename": item["filename"], "status": "uploaded", "bytes_uploaded": item["size_bytes"]}
    destination = batch_dir(CONFIG, run_id, batch_id) / item["filename"]
    temporary = destination.with_name(destination.name + ".part")
    received = 0
    try:
        async with await anyio.open_file(temporary, "wb") as handle:
            async for chunk in request.stream():
                received += len(chunk)
                if received > item["size_bytes"] or received > CONFIG.max_upload_file_bytes:
                    raise upload_error("file_too_large", f"{item['filename']} exceeds its declared size or file limit", item["filename"], 413)
                await handle.write(chunk)
        if received != item["size_bytes"]:
            raise upload_error("size_mismatch", f"{item['filename']} uploaded {received} of {item['size_bytes']} declared bytes", item["filename"])
        await run_in_threadpool(temporary.replace, destination)
    except BaseException:
        await run_in_threadpool(temporary.unlink, missing_ok=True)
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(finish_batch_file_transfer, CONFIG, project_id, run_id, batch_id, file_index, "pending")
        raise
    await run_in_threadpool(finish_batch_file_transfer, CONFIG, project_id, run_id, batch_id, file_index, "uploaded")
    return {"batch_id": batch_id, "filename": item["filename"], "status": "uploaded", "bytes_uploaded": received}


@app.post("/api/projects/{project_id}/runs/{run_id}/batches/{batch_id}/complete")
def finalize_upload_batch(project_id: str, run_id: str, batch_id: str, request: Request) -> dict:
    run = authorized_upload_run(project_id, run_id, request, require_editable=False)
    return complete_upload_batch(CONFIG, run, batch_id)


@app.delete("/api/projects/{project_id}/runs/{run_id}/batches/{batch_id}")
def cancel_staged_upload_batch(project_id: str, run_id: str, batch_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "upload")
    run = get_run(CONFIG, run_id)
    if run["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return cancel_upload_batch(CONFIG, run, batch_id)


@app.post("/api/runs/{run_id}/queue")
def queue_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "analyze")
    with project_upload_lock(CONFIG, project["id"]):
        run = get_run(CONFIG, run_id)
        if run["status"] not in {"created", "uploaded", "retrying"}:
            raise upload_error("run_not_ready", "Analysis cannot be queued from this state")
        queued = update_run(CONFIG, run_id, status="queued", status_message="Analysis queued")
        job = create_job_record(CONFIG, queued, principal["user_id"])
    queued["job"] = job
    return queued


@app.get("/api/jobs")
def list_jobs_api(request: Request, status: str | None = None, run_id: str | None = None) -> dict:
    principal = principal_from_request(request, CONFIG)
    if run_id:
        run = get_run(CONFIG, run_id)
        project = project_for_run(run)
        assert_project_access(CONFIG, project, principal, "view")
        return {"jobs": list_jobs(CONFIG, status=status, run_id=run_id)}
    visible_project_ids = {project["id"] for project in list_projects(CONFIG, principal)}
    return {
        "jobs": [
            job for job in list_jobs(CONFIG, status=status) if job.get("project_id") in visible_project_ids
        ]
    }


@app.get("/api/jobs/{job_id}")
def get_job_api(job_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    job = get_job(CONFIG, job_id)
    project = get_project(CONFIG, job["project_id"])
    assert_project_access(CONFIG, project, principal, "view")
    return job


@app.post("/api/runs/{run_id}/analyze")
def analyze_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "analyze")
    return run_analysis_workflow(run_id)


@app.post("/api/runs/{run_id}/recommendation")
def create_run_recommendation(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "analyze")
    recommendation = recommend_workflow(
        run_id=run_id,
        workflow_type=run.get("workflow_type", "terrain"),
        parameters=run.get("parameters", {}),
        inputs=run.get("inputs", []),
    )
    return update_run(CONFIG, run_id, recommendation=recommendation)["recommendation"]


@app.get("/api/runs/{run_id}/recommendation")
def get_run_recommendation(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    recommendation = run.get("recommendation")
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation


@app.post("/api/runs/{run_id}/recommendation/approve")
def approve_run_recommendation(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "analyze")
    recommendation = run.get("recommendation")
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if recommendation.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail="Recommendation is not pending approval")
    recommendation = dict(recommendation)
    recommendation.update({"status": "approved", "approved_by_user_id": principal["user_id"], "approved_at": utc_now()})
    return update_run(CONFIG, run_id, recommendation=recommendation, workflow_type=recommendation["workflow_type"])


@app.post("/api/runs/{run_id}/retry")
def retry_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    source_run = get_run(CONFIG, run_id)
    project = project_for_run(source_run)
    assert_project_access(CONFIG, project, principal, "retry")
    if source_run.get("status") != "failed" or not source_run.get("retryable"):
        raise HTTPException(status_code=400, detail="Run is not retryable")
    retry = create_run_record(
        CONFIG,
        project,
        principal["user_id"],
        workflow_type=source_run.get("workflow_type", "terrain"),
        name=f"Retry of {source_run.get('name', run_id)}",
        parameters=source_run.get("parameters", {}),
        retry_of_run_id=run_id,
        attempt_number=int(source_run.get("attempt_number", 1)) + 1,
    )
    # Carry forward only inputs that remain usable. Invalid records have no
    # stored path and must not reserve a filename on the fresh retry run.
    retry["inputs"] = [
        item for item in source_run.get("inputs", [])
        if item.get("status") == "valid" and item.get("path") and Path(item["path"]).is_file()
    ]
    retry = update_run(
        CONFIG,
        retry["run_id"],
        status="retrying",
        status_message="Retry created from failed run",
        inputs=retry["inputs"],
    )
    retry = update_run(CONFIG, retry["run_id"], status="queued", status_message="Retry queued")
    retry["job"] = create_job_record(CONFIG, retry, principal["user_id"])
    return retry


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "cancel")
    with project_upload_lock(CONFIG, project["id"]):
        run = get_run(CONFIG, run_id)
        if run["status"] not in {"created", "queued", "running"}:
            raise HTTPException(status_code=400, detail="Only created, queued, or running runs can be canceled")
        return update_run(CONFIG, run_id, status="canceled", status_message="Run canceled")


@app.post("/api/runs/{run_id}/report")
def generate_report(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    metadata = get_run(CONFIG, run_id)
    project = project_for_run(metadata)
    assert_project_access(CONFIG, project, principal, "report")
    dem_path = first_valid_dem(metadata)
    outputs = metadata.get("outputs", {})

    required = {
        "slope": outputs.get("slope"),
        "hillshade": outputs.get("hillshade"),
        "terrain_risk": outputs.get("terrain_risk"),
    }
    missing = [name for name, value in required.items() if not value or not Path(value).exists()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Run analysis before report generation. Missing: {', '.join(missing)}",
        )

    report_path = run_dir(CONFIG, run_id) / "reports" / "terrain_analysis.md"
    write_markdown_report(
        TerrainReportInputs(
            dem_path=dem_path or Path(""),
            slope_path=Path(required["slope"]),
            hillshade_path=Path(required["hillshade"]),
            terrain_risk_path=Path(required["terrain_risk"]),
            paraview_render_path=None,
            paraview_state_path=None,
        ),
        report_path,
    )

    outputs["report_md"] = str(report_path)
    metadata = update_run(CONFIG, run_id, status="reported", status_message="Report generated", outputs=outputs)
    metadata["report_url"] = f"/api/runs/{run_id}/outputs/report_md/download"
    return metadata


def report_comment_context(run_id: str, request: Request) -> tuple[dict, dict, dict[str, str]]:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    return run, project, principal


@app.get("/api/runs/{run_id}/report/comments")
def list_report_comments_api(run_id: str, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return list_report_comments(CONFIG, run, project, principal)


@app.post("/api/runs/{run_id}/report/comments")
def create_report_comment_api(run_id: str, payload: ReportCommentCreate, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return create_report_comment(CONFIG, run, project, principal, payload.body_markdown)


@app.get("/api/runs/{run_id}/report/comments/{comment_id}")
def get_report_comment_api(run_id: str, comment_id: str, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return get_report_comment(CONFIG, run, project, principal, comment_id)


@app.patch("/api/runs/{run_id}/report/comments/{comment_id}")
def update_report_comment_api(run_id: str, comment_id: str, payload: ReportCommentUpdate, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return update_report_comment(CONFIG, run, project, principal, comment_id, payload.body_markdown)


@app.post("/api/runs/{run_id}/report/comments/{comment_id}/resolve")
def resolve_report_comment_api(run_id: str, comment_id: str, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return moderate_report_comment(CONFIG, run, project, principal, comment_id, "resolve")


@app.post("/api/runs/{run_id}/report/comments/{comment_id}/reopen")
def reopen_report_comment_api(run_id: str, comment_id: str, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return moderate_report_comment(CONFIG, run, project, principal, comment_id, "reopen")


@app.delete("/api/runs/{run_id}/report/comments/{comment_id}")
def delete_report_comment_api(run_id: str, comment_id: str, request: Request) -> dict:
    run, project, principal = report_comment_context(run_id, request)
    return moderate_report_comment(CONFIG, run, project, principal, comment_id, "delete")


@app.get("/api/runs")
def list_all_runs(request: Request, project_id: str | None = None) -> dict:
    principal = principal_from_request(request, CONFIG)
    if project_id:
        project = get_project(CONFIG, project_id)
        assert_project_access(CONFIG, project, principal, "view")
        return {"runs": list_runs(CONFIG, project_id)}
    return {"runs": list_visible_runs(CONFIG, principal)}


@app.get("/api/runs/{run_id}")
def get_run_api(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    return run


@app.get("/api/runs/{run_id}/outputs")
def list_outputs(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    files = list_output_artifacts(CONFIG, run)
    return {"project_id": run["project_id"], "run_id": run_id, "files": files}


@app.get("/api/runs/{run_id}/outputs/{output_key:path}/download")
def download_output(run_id: str, output_key: str, request: Request) -> FileResponse:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    path = registered_output_path(CONFIG, run, output_key)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file missing")
    return FileResponse(
        path,
        media_type=mime_type_for_path(path),
        filename=path.name,
        content_disposition_type="attachment",
    )


@app.get("/api/runs/{run_id}/outputs/{output_key:path}/preview")
def preview_output(run_id: str, output_key: str, request: Request) -> FileResponse:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    path = registered_output_path(CONFIG, run, output_key)
    if path.suffix.lower() != ".png":
        raise HTTPException(status_code=400, detail="Only PNG outputs can be previewed")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file missing")
    return FileResponse(path, media_type="image/png", filename=path.name, content_disposition_type="inline")


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(project_id: str, request: Request) -> str:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "view")
    runs = list_runs(CONFIG, project_id)
    run_rows = "\n".join(
        "<tr>"
        f"<td><a href='/runs/{run['run_id']}'>{escape(run['name'])}</a></td>"
        f"<td><code>{escape(run['status'])}</code></td>"
        f"<td>{escape(run.get('created_by_user_id') or '')}</td>"
        f"<td>{escape(run.get('created_at') or '')}</td>"
        f"<td>{escape(run.get('updated_at') or '')}</td>"
        f"<td>{len(run.get('inputs', []))}</td>"
        f"<td>{len([value for value in run.get('outputs', {}).values() if value])}</td>"
        "</tr>"
        for run in runs
    ) or "<tr><td colspan='7'>No runs yet</td></tr>"
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{escape(project['name'])}</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border-bottom: 1px solid #ddd; padding: .45rem; text-align: left; }}
      code {{ background: #f4f4f4; padding: .1rem .3rem; }}
    </style>
  </head>
  <body>
    <h1>{escape(project['name'])}</h1>
    <p>{escape(project.get('description', ''))}</p>
    <form method="post" action="/dashboard/projects/{project_id}/runs">
      <label>Analysis name<input name="name" placeholder="Run name" required></label>
      <label>Workflow<select name="workflow_type">
        <option value="terrain">Terrain analysis</option>
        <option value="flood_risk">Flood risk</option>
        <option value="wildfire_risk">Wildfire risk</option>
      </select></label>
      <button>New analysis</button>
    </form>
    <h2>Runs</h2>
    <table>
      <thead><tr><th>Name</th><th>Status</th><th>Owner</th><th>Created</th><th>Updated</th><th>Files</th><th>Outputs</th></tr></thead>
      <tbody>{run_rows}</tbody>
    </table>
  </body>
</html>
"""


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str, request: Request) -> str:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "view")
    jobs = list_jobs(CONFIG, run_id=run_id)
    artifacts = list_output_artifacts(CONFIG, run)

    def artifact_rows(category: str) -> str:
        rows = []
        for artifact in artifacts:
            if artifact["category"] != category:
                continue
            checksum = artifact.get("checksum_sha256") or "missing"
            size = artifact.get("size_bytes")
            size_label = f"{size:,}" if size is not None else "missing"
            preview = (
                f"<a href='{escape(artifact['preview_url'])}'>Preview</a>"
                if artifact.get("preview_url") and artifact.get("exists")
                else ""
            )
            download = (
                f"<a href='{escape(artifact['download_url'])}'>Download</a>"
                if artifact.get("exists")
                else "<span>Missing file</span>"
            )
            preview_image = (
                f"<div><a href='{escape(artifact['preview_url'])}'>"
                f"<img src='{escape(artifact['preview_url'])}' alt='{escape(artifact['filename'])}'></a></div>"
                if category == "render" and artifact.get("preview_url") and artifact.get("exists")
                else ""
            )
            rows.append(
                "<tr>"
                f"<td>{escape(artifact['output_type'])}{preview_image}</td>"
                f"<td><code>{escape(artifact['mime_type'])}</code></td>"
                f"<td>{size_label}</td>"
                f"<td><code>{escape(checksum)}</code></td>"
                f"<td>{escape(artifact['generated_stage'])}</td>"
                f"<td><code>{escape(artifact['display_filename'])}</code></td>"
                f"<td>{preview} {download}</td>"
                "</tr>"
            )
        return "".join(rows) or "<tr><td colspan='7'>No outputs in this category</td></tr>"

    inputs = [
        "<tr>"
        f"<td>{escape(item.get('original_filename') or item.get('stored_filename') or '')}</td>"
        f"<td><code>{escape(item.get('status') or '')}</code></td>"
        f"<td>{escape(item.get('file_type') or '')}</td>"
        f"<td>{item.get('size_bytes') or 0}</td>"
        f"<td>{escape('; '.join([error.get('error_message', '') for error in item.get('validation_errors', [])] + [warning.get('message', '') for warning in item.get('warnings', [])]))}</td>"
        "</tr>"
        for item in run.get("inputs", [])
    ]
    job_rows = [
        "<tr>"
        f"<td><code>{escape(job.get('status') or '')}</code></td>"
        f"<td>{escape(job.get('job_type') or '')}</td>"
        f"<td>{escape(job.get('updated_at') or '')}</td>"
        f"<td>{escape(job.get('error_message') or '')}</td>"
        f"<td>{escape(job.get('logs_path') or '')}</td>"
        "</tr>"
        for job in jobs
    ]
    history = "\n".join(
        f"<li><code>{escape(item['status'])}</code> {escape(item['at'])} {escape(item.get('message', ''))}</li>"
        for item in run.get("status_history", [])
    )
    actions = []
    if run.get("status") in {"created", "uploaded", "retrying"}:
        actions.append(f"<form method='post' action='/dashboard/runs/{run_id}/queue'><button>Queue</button></form>")
    if run.get("status") in {"created", "queued", "running"}:
        actions.append(f"<form method='post' action='/dashboard/runs/{run_id}/cancel'><button>Cancel</button></form>")
    if run.get("status") == "failed" and run.get("retryable"):
        actions.append(f"<form method='post' action='/dashboard/runs/{run_id}/retry'><button>Retry</button></form>")
    upload_form = ""
    if run.get("status") in {"created", "uploaded", "retrying"}:
        upload_form = f"""
    <h2>Upload Input</h2>
    <p>Select datasets together. For a Shapefile, select its .shp, .shx, and .dbf files (and .prj when available) in one batch.</p>
    <p>Limits: {CONFIG.max_upload_file_bytes // (1024 * 1024)} MB per file; {CONFIG.max_upload_batch_bytes // (1024 * 1024)} MB per batch; {CONFIG.max_batch_files} files per batch; {CONFIG.max_project_bytes // (1024 * 1024)} MB per project.</p>
    <form id="batch-upload" class="upload-form" data-api="/api/projects/{run['project_id']}/runs/{run_id}" data-max-file="{CONFIG.max_upload_file_bytes}" data-max-batch="{CONFIG.max_upload_batch_bytes}" data-max-files="{CONFIG.max_batch_files}">
      <label>Choose files<input type="file" name="files" multiple accept=".tif,.tiff,.geojson,.json,.csv,.shp,.shx,.dbf,.prj,.cpg,.qix,.sbn,.sbx,.xml" required></label>
      <button type="submit">Upload and validate</button>
      <button type="button" id="cancel-upload" hidden>Cancel upload</button>
      <progress max="100" value="0" aria-label="Upload progress"></progress>
      <p role="status" aria-live="polite">No upload started.</p>
      <ul id="upload-results"></ul>
    </form>
    {BATCH_UPLOAD_SCRIPT}
"""
    recommendation = run.get("recommendation")
    recommendation_markup = ""
    if recommendation:
      recommendation_actions = ""
      if recommendation.get("status") == "pending_approval":
        recommendation_actions = (
          f"<form method='post' action='/dashboard/runs/{run_id}/recommendation/approve'>"
          "<button>Approve recommendation</button></form>"
        )
      recommendation_markup = f"""
    <h2>GeoMiniLM Recommendation</h2>
    <p>Status: <code>{escape(recommendation.get('status') or '')}</code> |
       Confidence: <code>{escape(str(recommendation.get('confidence', 'n/a')))}</code></p>
    <p>{escape(recommendation.get('explanation') or '')}</p>
    <p>Suggested workflow: <code>{escape(recommendation.get('workflow_type') or '')}</code></p>
    <p>Parameters: <code>{escape(json.dumps(recommendation.get('parameters', {}), sort_keys=True))}</code></p>
    <pre>{escape(json.dumps(recommendation.get('predicted_workflow', []), indent=2))}</pre>
    <div><form method='post' action='/dashboard/runs/{run_id}/recommendation'>
      <button>Refresh recommendation</button></form>{recommendation_actions}</div>
  """
    else:
      recommendation_markup = f"""
    <h2>GeoMiniLM Recommendation</h2>
    <p>No recommendation has been generated for this run.</p>
    <form method='post' action='/dashboard/runs/{run_id}/recommendation'>
      <button>Generate recommendation</button>
    </form>
  """
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{escape(run['name'])}</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
      table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
      th, td {{ border-bottom: 1px solid #ddd; padding: .45rem; text-align: left; vertical-align: top; }}
      code {{ background: #f4f4f4; padding: .1rem .3rem; }}
      form {{ display: inline-block; margin-right: .5rem; }}
      label, input, textarea {{ display: block; width: 100%; box-sizing: border-box; font: inherit; margin: .25rem 0; }}
      .upload-form {{ display: block; max-width: 42rem; margin: 1rem 0; }}
      img {{ max-width: 320px; max-height: 220px; display: block; margin-top: .5rem; border: 1px solid #ddd; }}
      .checksum {{ max-width: 24rem; overflow-wrap: anywhere; }}
    </style>
  </head>
  <body>
    <h1>{escape(run['name'])}</h1>
    <p>Status: <code>{escape(run['status'])}</code></p>
    <p>Owner: {escape(run.get('created_by_user_id') or '')}</p>
    <p>Created: {escape(run.get('created_at') or '')}</p>
    <p>Updated: {escape(run.get('updated_at') or '')}</p>
    <p>Error: {escape(run.get('error_message') or '')}</p>
    <div>{''.join(actions)}</div>
    {upload_form}
    {recommendation_markup}
    <h2>Inputs</h2>
    <table>
      <thead><tr><th>File</th><th>Status</th><th>Type</th><th>Bytes</th><th>Validation feedback</th></tr></thead>
      <tbody>{''.join(inputs) or "<tr><td colspan='5'>No inputs yet</td></tr>"}</tbody>
    </table>
    <h2>Jobs</h2>
    <table>
      <thead><tr><th>Status</th><th>Type</th><th>Updated</th><th>Error</th><th>Log</th></tr></thead>
      <tbody>{''.join(job_rows) or "<tr><td colspan='5'>No jobs yet</td></tr>"}</tbody>
    </table>
    <h2>Outputs</h2>
    <h3>Raster Outputs</h3>
    <table>
      <thead><tr><th>Output</th><th>MIME</th><th>Bytes</th><th>Checksum</th><th>Stage</th><th>File</th><th>Actions</th></tr></thead>
      <tbody>{artifact_rows("raster")}</tbody>
    </table>
    <h3>Vector Outputs</h3>
    <table>
      <thead><tr><th>Output</th><th>MIME</th><th>Bytes</th><th>Checksum</th><th>Stage</th><th>File</th><th>Actions</th></tr></thead>
      <tbody>{artifact_rows("vector")}</tbody>
    </table>
    <h3>Render and Preview Outputs</h3>
    <table>
      <thead><tr><th>Output</th><th>MIME</th><th>Bytes</th><th>Checksum</th><th>Stage</th><th>File</th><th>Actions</th></tr></thead>
      <tbody>{artifact_rows("render")}</tbody>
    </table>
    <h3>Metadata and Summary Outputs</h3>
    <table>
      <thead><tr><th>Output</th><th>MIME</th><th>Bytes</th><th>Checksum</th><th>Stage</th><th>File</th><th>Actions</th></tr></thead>
      <tbody>{artifact_rows("metadata")}</tbody>
    </table>
    <h2>History</h2>
    <ul>{history}</ul>
  </body>
</html>
"""


@app.post("/dashboard/runs/{run_id}/queue")
def queue_run_form(run_id: str, request: Request) -> HTMLResponse:
    queue_run(run_id, request)
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run_id}'>")


@app.post("/dashboard/runs/{run_id}/cancel")
def cancel_run_form(run_id: str, request: Request) -> HTMLResponse:
    cancel_run(run_id, request)
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run_id}'>")


@app.post("/dashboard/runs/{run_id}/retry")
def retry_run_form(run_id: str, request: Request) -> HTMLResponse:
    retry = retry_run(run_id, request)
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{retry['run_id']}'>")


@app.post("/dashboard/runs/{run_id}/recommendation")
def create_recommendation_form(run_id: str, request: Request) -> HTMLResponse:
    create_run_recommendation(run_id, request)
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run_id}'>")


@app.post("/dashboard/runs/{run_id}/recommendation/approve")
def approve_recommendation_form(run_id: str, request: Request) -> HTMLResponse:
    approve_run_recommendation(run_id, request)
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run_id}'>")


# Dashboard form conveniences. They intentionally use local-dev identity in
# file-only mode, while production API calls can require headers through config.
@app.post("/dashboard/projects")
async def create_project_form(request: Request) -> HTMLResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    principal = principal_from_request(request, CONFIG)
    project = create_project(
        CONFIG,
        form.get("name", ["Untitled Project"])[0],
        principal["user_id"],
        form.get("description", [""])[0],
    )
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/projects/{project['id']}'>")


@app.post("/dashboard/projects/{project_id}/runs")
async def create_run_form(project_id: str, request: Request) -> HTMLResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "create_run")
    run = create_run_record(
        CONFIG, project, principal["user_id"],
        name=form.get("name", ["Terrain Run"])[0],
        workflow_type=form.get("workflow_type", ["terrain"])[0],
    )
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run['run_id']}'>")


@app.post("/dashboard/projects/{project_id}/runs/{run_id}/files")
async def upload_run_file_form(project_id: str, run_id: str, request: Request) -> HTMLResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(CONFIG, project, principal, "upload")
    run = get_run(CONFIG, run_id)
    if run["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    ingest_base64_files(
        CONFIG,
        run,
        [
            {
                "filename": form.get("filename", [""])[0],
                "content_b64": form.get("content_b64", [""])[0],
                "content_type": form.get("content_type", [""])[0] or None,
            }
        ],
    )
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run_id}'>")


# Compatibility endpoints retained for the original README curl flow.
@app.post("/api/runs")
def create_run_compat(request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    projects = list_projects(CONFIG, principal)
    project = projects[0] if projects else create_project(CONFIG, "Local Demo Project", principal["user_id"])
    return create_run_record(CONFIG, project, principal["user_id"])


@app.post("/api/runs/{run_id}/upload-dem")
async def upload_dem_compat(
    run_id: str,
    request: Request,
    filename: str = Query(default="dem.tif", description="Filename to use for uploaded DEM bytes."),
) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "upload")
    normalized = normalize_filename(filename)
    with tempfile.TemporaryDirectory(dir=run_dir(CONFIG, run_id)) as temporary:
        path = Path(temporary) / normalized
        received = 0
        async with await anyio.open_file(path, "wb") as handle:
            async for chunk in request.stream():
                received += len(chunk)
                if received > CONFIG.max_upload_file_bytes:
                    raise upload_error("file_too_large", f"{normalized} exceeds the {CONFIG.max_upload_file_bytes} byte file limit", normalized, 413)
                await handle.write(chunk)
        return (await run_in_threadpool(ingest_file_paths, CONFIG, run, [(filename, path, request.headers.get("content-type"))]))["run"]


def copy_sample_dem_to_run_compat(run_id: str, sample_dem: Path = Path("data/sample/sample_dem.tif")) -> dict:
    return copy_sample_dem_to_run(CONFIG, run_id, sample_dem)


@app.post("/api/runs/{run_id}/use-sample-dem")
def use_sample_dem(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(CONFIG, project, principal, "upload")
    return copy_sample_dem_to_run_compat(run_id)


def write_legacy_run_metadata(run_id: str) -> dict:
    base_dir = run_dir(CONFIG, run_id)
    create_run_folders(base_dir)
    metadata = {
        "run_id": run_id,
        "status": "created",
        "created_at": "",
        "updated_at": "",
        "paths": {"run_dir": str(base_dir)},
        "outputs": {},
    }
    write_json(run_metadata_path(CONFIG, run_id), metadata)
    return metadata
