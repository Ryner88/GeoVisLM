from __future__ import annotations

import base64
import json
import secrets
from html import escape
from urllib.parse import quote
from urllib.parse import parse_qs
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    DASHBOARD_SESSION_COOKIE,
    assert_project_access,
    copy_sample_dem_to_run,
    authenticate_user,
    create_dashboard_session,
    create_job_record,
    create_project,
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
    list_jobs,
    list_output_artifacts,
    list_projects,
    list_runs,
    list_visible_runs,
    mime_type_for_path,
    principal_from_request,
    public_user,
    registered_output_path,
    run_dir,
    run_metadata_path,
    update_run,
    valid_vector_inputs,
    write_json,
)
from geovis_lm.dashboard.analysis_adapter import (
    AnalysisExecutionError,
    execute_dem_analysis,
    execute_flood_analysis,
    execute_wildfire_analysis,
)
from geovis_lm.reports.terrain_report import TerrainReportInputs, write_markdown_report


CONFIG = DashboardConfig.from_env()
ensure_storage(CONFIG)

app = FastAPI(title="GeoVisLM Dashboard", version="0.2.0")


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
    response.delete_cookie(DASHBOARD_SESSION_COOKIE)
    return response


def project_for_run(run: dict) -> dict:
    return get_project(CONFIG, run["project_id"])


def run_analysis_workflow(run_id: str) -> dict:
    metadata = get_run(CONFIG, run_id)
    dem_path = first_valid_dem(metadata)
    if not dem_path or not dem_path.exists():
        return update_run(
            CONFIG,
            run_id,
            status="failed",
            status_message="No valid DEM input found",
            error_code="missing_dem",
            error_message="Upload a valid DEM before analysis",
            retryable=True,
        )

    workflow_type = metadata.get("workflow_type", "terrain")
    workflow_labels = {
        "terrain": "Terrain analysis",
        "flood_risk": "Flood risk analysis",
        "wildfire_risk": "Wildfire risk analysis",
    }
    workflow_label = workflow_labels.get(workflow_type, "Terrain analysis")
    update_run(CONFIG, run_id, status="running", status_message=f"{workflow_label} started")

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
        return update_run(
            CONFIG,
            run_id,
            status="failed",
            status_message=f"{workflow_label} failed",
            error_code=exc.error_code,
            error_message=exc.error_message,
            error_detail=json.dumps(exc.as_detail(), sort_keys=True),
            retryable=exc.retryable,
        )
    except Exception as exc:
        return update_run(
            CONFIG,
            run_id,
            status="failed",
            status_message=f"{workflow_label} failed",
            error_code="dem_analysis_failed",
            error_message=str(exc),
            error_detail=repr(exc),
            retryable=True,
        )

    return update_run(
        CONFIG,
        run_id,
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
    assert_project_access(project, principal, "view")
    return project


@app.post("/api/projects/{project_id}/runs")
def create_project_run(project_id: str, payload: RunCreate, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(project, principal, "create_run")
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
    assert_project_access(project, principal, "view")
    return {"project_id": project_id, "runs": list_runs(CONFIG, project_id)}


@app.post("/api/projects/{project_id}/runs/{run_id}/files")
def upload_project_run_files(project_id: str, run_id: str, payload: BatchUploadPayload, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(project, principal, "upload")
    run = get_run(CONFIG, run_id)
    if run["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return ingest_base64_files(CONFIG, run, [item.model_dump() for item in payload.files])


@app.post("/api/runs/{run_id}/queue")
def queue_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(project, principal, "analyze")
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
        assert_project_access(project, principal, "view")
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
    assert_project_access(project, principal, "view")
    return job


@app.post("/api/runs/{run_id}/analyze")
def analyze_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(project, principal, "analyze")
    return run_analysis_workflow(run_id)


@app.post("/api/runs/{run_id}/retry")
def retry_run(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    source_run = get_run(CONFIG, run_id)
    project = project_for_run(source_run)
    assert_project_access(project, principal, "retry")
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
    retry["inputs"] = source_run.get("inputs", [])
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
    assert_project_access(project, principal, "cancel")
    if run["status"] not in {"created", "queued", "running"}:
        raise HTTPException(status_code=400, detail="Only created, queued, or running runs can be canceled")
    return update_run(CONFIG, run_id, status="canceled", status_message="Run canceled")


@app.post("/api/runs/{run_id}/report")
def generate_report(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    metadata = get_run(CONFIG, run_id)
    project = project_for_run(metadata)
    assert_project_access(project, principal, "report")
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


@app.get("/api/runs")
def list_all_runs(request: Request, project_id: str | None = None) -> dict:
    principal = principal_from_request(request, CONFIG)
    if project_id:
        project = get_project(CONFIG, project_id)
        assert_project_access(project, principal, "view")
        return {"runs": list_runs(CONFIG, project_id)}
    return {"runs": list_visible_runs(CONFIG, principal)}


@app.get("/api/runs/{run_id}")
def get_run_api(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(project, principal, "view")
    return run


@app.get("/api/runs/{run_id}/outputs")
def list_outputs(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(project, principal, "view")
    files = list_output_artifacts(CONFIG, run)
    return {"project_id": run["project_id"], "run_id": run_id, "files": files}


@app.get("/api/runs/{run_id}/outputs/{output_key:path}/download")
def download_output(run_id: str, output_key: str, request: Request) -> FileResponse:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(project, principal, "view")
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
    assert_project_access(project, principal, "view")
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
    assert_project_access(project, principal, "view")
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
      <input name="name" placeholder="Run name">
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
    assert_project_access(project, principal, "view")
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
        f"<td>{escape('; '.join(error.get('error_message', '') for error in item.get('validation_errors', [])))}</td>"
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
    <form method="post" action="/dashboard/projects/{run['project_id']}/runs/{run_id}/files" class="upload-form">
      <label>Filename<input name="filename" placeholder="sample_dem.tif" required></label>
      <label>MIME type<input name="content_type" placeholder="image/tiff"></label>
      <label>Base64 content<textarea name="content_b64" rows="5" required></textarea></label>
      <button>Upload input</button>
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
    <h2>Inputs</h2>
    <table>
      <thead><tr><th>File</th><th>Status</th><th>Type</th><th>Bytes</th><th>Errors</th></tr></thead>
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
    assert_project_access(project, principal, "create_run")
    run = create_run_record(CONFIG, project, principal["user_id"], name=form.get("name", ["Terrain Run"])[0])
    return HTMLResponse(f"<meta http-equiv='refresh' content='0; url=/runs/{run['run_id']}'>")


@app.post("/dashboard/projects/{project_id}/runs/{run_id}/files")
async def upload_run_file_form(project_id: str, run_id: str, request: Request) -> HTMLResponse:
    form = parse_qs((await request.body()).decode("utf-8"))
    principal = principal_from_request(request, CONFIG)
    project = get_project(CONFIG, project_id)
    assert_project_access(project, principal, "upload")
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
    assert_project_access(project, principal, "upload")

    chunks = []
    async for chunk in request.stream():
        chunks.append(chunk)
    content_b64 = base64.b64encode(b"".join(chunks)).decode("ascii")
    return ingest_base64_files(CONFIG, run, [{"filename": filename, "content_b64": content_b64}])["run"]


def copy_sample_dem_to_run_compat(run_id: str, sample_dem: Path = Path("data/sample/sample_dem.tif")) -> dict:
    return copy_sample_dem_to_run(CONFIG, run_id, sample_dem)


@app.post("/api/runs/{run_id}/use-sample-dem")
def use_sample_dem(run_id: str, request: Request) -> dict:
    principal = principal_from_request(request, CONFIG)
    run = get_run(CONFIG, run_id)
    project = project_for_run(run)
    assert_project_access(project, principal, "upload")
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
