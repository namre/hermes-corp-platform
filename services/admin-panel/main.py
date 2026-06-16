"""admin-panel — веб-панель оператора Hermes Corp Platform.

Агрегирует данные из corp-dir-broker и provisioner; остальные метрики —
правдоподобные mock-данные, помеченные source='sample'. Это образец-заглушка:
рабочий, читает что может из других сервисов, остальное — образцовые данные.

Порт: 8655.

Авторизация:
  - Если ADMIN_UI_PASSWORD задан — вход по паролю (cookie-сессия).
  - Если пуст — панель открыта с предупреждением в интерфейсе.

Env-переменные (все необязательны для запуска на моках):
  ADMIN_PANEL_BRAND       — название бренда в шапке (default: Corp AI)
  ADMIN_UI_PASSWORD       — пароль для входа (пусто = открытый доступ)
  CORP_DIR_URL            — URL corp-dir-broker (default: http://corp-dir-broker:8652)
  PROVISIONER_URL         — URL provisioner (default: http://provisioner:8650)
  BROKER_INTERNAL_AUTH    — общий секрет для x-internal-auth
  HERMES_IMAGE            — тег образа агента (для отображения в System)
"""

import hashlib
import json
import os
import random
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
BRAND = os.getenv("ADMIN_PANEL_BRAND", "Corp AI")
PASSWORD = os.getenv("ADMIN_UI_PASSWORD", "")
CORP_DIR_URL = os.getenv("CORP_DIR_URL", "http://corp-dir-broker:8652")
PROVISIONER_URL = os.getenv("PROVISIONER_URL", "http://provisioner:8650")
BROKER_AUTH = os.getenv("BROKER_INTERNAL_AUTH", "")
HERMES_IMAGE = os.getenv("HERMES_IMAGE", "your-registry/hermes-agent:latest")

# Простой in-memory store токенов сессий (dev-уровень)
_sessions: set[str] = set()

app = FastAPI(title="admin-panel", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(minutes: int = 0, hours: int = 0, days: int = 0) -> str:
    delta = timedelta(minutes=minutes, hours=hours, days=days)
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_session(session_token: str | None) -> bool:
    """Вернуть True если авторизован (или пароль не задан)."""
    if not PASSWORD:
        return True
    return session_token is not None and session_token in _sessions


async def _corp_dir_users() -> list[dict]:
    """Запросить список сотрудников из corp-dir-broker. При недоступности — пустой список."""
    headers = {}
    if BROKER_AUTH:
        headers["x-internal-auth"] = BROKER_AUTH
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{CORP_DIR_URL}/org-structure", headers=headers)
            resp.raise_for_status()
            return resp.json().get("employees", [])
    except Exception:
        return []


async def _provisioner_runtimes() -> list[dict] | None:
    """Запросить список runtime из provisioner.
    TODO: provisioner не имеет GET /runtimes — добавьте эндпоинт и замените заглушку.
    """
    # Пытаемся проверить здоровье provisioner'а, чтобы знать, доступен ли он
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{PROVISIONER_URL}/health")
            if resp.status_code == 200:
                return []  # TODO: заменить на GET /runtimes когда эндпоинт появится
    except Exception:
        pass
    return None  # недоступен


# ---------------------------------------------------------------------------
# Mock-данные (source='sample')
# ---------------------------------------------------------------------------

def _mock_metrics_for_user(email: str) -> dict:
    """Детерминированные псевдослучайные метрики на основе хэша email."""
    seed = int(hashlib.md5(email.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    statuses = ["active", "active", "active", "idle", "inactive"]
    return {
        "webui_7d": rng.randint(0, 120),
        "tg_7d": rng.randint(0, 80),
        "storage_mb": round(rng.uniform(10, 500), 1),
        "last_seen": _ago(hours=rng.randint(1, 72 * 24)),
        "status": rng.choice(statuses),
        "source": "sample",
    }


def _mock_system() -> dict:
    return {
        "image": HERMES_IMAGE,
        "registry_note": "Replace with your actual registry/image in HERMES_IMAGE env",
        "containers_running": 5,
        "containers_total": 7,
        "disk_used_gb": 38.4,
        "disk_total_gb": 200.0,
        "disk_pct": 19.2,
        "mux_queue_depth": 3,
        "mux_queue_max": 50,
        "containers": [
            {"name": "hermes-agent",         "image": "your-registry/hermes-agent:latest",    "status": "running", "port": 8642},
            {"name": "identity-proxy",        "image": "hermes-identity-proxy:latest",          "status": "running", "port": 8643},
            {"name": "provisioner",           "image": "hermes-provisioner:latest",             "status": "running", "port": 8650},
            {"name": "corp-dir-broker",       "image": "your-registry/corp-dir-broker:latest", "status": "running", "port": 8652},
            {"name": "key-broker",            "image": "your-registry/key-broker:latest",       "status": "running", "port": 8700},
            {"name": "hermes-u-alice",        "image": "your-registry/hermes-agent:latest",    "status": "running", "port": None},
            {"name": "hermes-u-bob",          "image": "your-registry/hermes-agent:latest",    "status": "stopped", "port": None},
        ],
        "source": "sample",
    }


def _mock_channels(users: list[dict]) -> list[dict]:
    rows = []
    for u in users:
        seed = int(hashlib.md5(u["email"].encode()).hexdigest()[:8], 16)
        rng = random.Random(seed + 1)
        rows.append({
            "email": u["email"],
            "full_name": u.get("full_name", u["email"]),
            "webui_today": rng.randint(0, 30),
            "webui_7d": rng.randint(0, 150),
            "tg_today": rng.randint(0, 20),
            "tg_7d": rng.randint(0, 80),
            "last_channel": rng.choice(["WebUI", "Telegram", "WebUI", "—"]),
        })
    return rows


def _mock_integrations(users: list[dict]) -> list[dict]:
    rows = []
    for u in users:
        seed = int(hashlib.md5(u["email"].encode()).hexdigest()[:8], 16)
        rng = random.Random(seed + 2)
        rows.append({
            "email": u["email"],
            "full_name": u.get("full_name", u["email"]),
            "directory": rng.randint(0, 50),
            "files": rng.randint(0, 200),
            "tasks": rng.randint(0, 100),
            "memory": rng.randint(0, 300),
            "onboarding": rng.randint(0, 10),
        })
    return rows


def _mock_audit() -> list[dict]:
    events = [
        {"event_type": "a2a.status_check",     "actor": {"type": "agent",  "id": "acct-bot"},          "subject": {"type": "user", "id": "alice@example.com"}, "action": "status_check",      "outcome": "allowed",  "tags": ["a2a_session"],              "ts_offset_min": 5},
        {"event_type": "provisioner.create",    "actor": {"type": "system", "id": "provisioner"},       "subject": {"type": "user", "id": "bob@example.com"},   "action": "container_create",  "outcome": "allowed",  "tags": ["privileged"],               "ts_offset_min": 18},
        {"event_type": "security.injection",    "actor": {"type": "user",   "id": "unknown"},            "subject": {"type": "proxy","id": "identity-proxy"},    "action": "blocked_request",   "outcome": "denied",   "tags": ["security"],                 "ts_offset_min": 42},
        {"event_type": "broker.files.read",     "actor": {"type": "agent",  "id": "hermes-u-alice"},    "subject": {"type": "user", "id": "alice@example.com"}, "action": "list_files",        "outcome": "allowed",  "tags": ["pii", "a2a_session"],       "ts_offset_min": 67},
        {"event_type": "audit.redact",          "actor": {"type": "user",   "id": "carol@example.com"}, "subject": {"type": "audit","id": "aud_sample_01"},      "action": "mark_redacted",     "outcome": "allowed",  "tags": ["privileged"],               "ts_offset_min": 120},
        {"event_type": "provisioner.stop",      "actor": {"type": "system", "id": "idle-shutdown"},     "subject": {"type": "user", "id": "bob@example.com"},   "action": "container_stop",    "outcome": "allowed",  "tags": ["cron"],                     "ts_offset_min": 180},
        {"event_type": "key_broker.issue",      "actor": {"type": "system", "id": "provisioner"},       "subject": {"type": "user", "id": "carol@example.com"}, "action": "issue_virtual_key", "outcome": "allowed",  "tags": ["privileged"],               "ts_offset_min": 240},
        {"event_type": "a2a.consent_granted",   "actor": {"type": "user",   "id": "alice@example.com"}, "subject": {"type": "agent","id": "tasks-bot"},          "action": "consent_grant",     "outcome": "allowed",  "tags": ["a2a_session", "pii"],       "ts_offset_min": 310},
    ]
    result = []
    for i, ev in enumerate(events):
        offset = ev.pop("ts_offset_min")
        result.append({
            "audit_id": f"aud_sample_{i:02d}",
            "ts": _ago(minutes=offset),
            "source": "sample",
            **ev,
            "session_id": f"sess_sample_{i:02d}",
            "request_id": f"req_sample_{i:02d}",
            "redacted": False,
            "legal_basis": "legitimate_interest" if "pii" in ev.get("tags", []) else None,
        })
    return result


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    err_html = f'<p class="error">{error}</p>' if error else ""
    return HTMLResponse(_login_html(err_html))


@app.post("/login")
async def do_login(request: Request):
    form = await request.form()
    pwd = form.get("password", "")
    if not PASSWORD or pwd == PASSWORD:
        token = secrets.token_hex(32)
        _sessions.add(token)
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
        return resp
    return RedirectResponse("/login?error=Неверный+пароль", status_code=302)


@app.get("/logout")
async def logout(session_token: str | None = Cookie(default=None)):
    if session_token and session_token in _sessions:
        _sessions.discard(session_token)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session_token")
    return resp


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(session_token: str | None = Cookie(default=None)):
    if PASSWORD and not _check_session(session_token):
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(_dashboard_html())


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/users")
async def api_users(session_token: str | None = Cookie(default=None)):
    if PASSWORD and not _check_session(session_token):
        raise HTTPException(status_code=401, detail="not authenticated")

    employees = await _corp_dir_users()
    runtimes = await _provisioner_runtimes()
    runtime_available = runtimes is not None

    result = []
    for emp in employees:
        metrics = _mock_metrics_for_user(emp["email"])
        # TODO: если provisioner добавит GET /runtimes — подтяни реальный статус контейнера
        runtime_status = "n/a"  # provisioner/GET /runtimes не реализован
        result.append({
            **emp,
            "runtime_status": runtime_status,
            "runtime_note": "TODO: provisioner GET /runtimes not yet implemented",
            **metrics,
        })

    return {
        "source_users": "corp-dir-broker" if employees else "sample",
        "source_metrics": "sample",
        "runtime_available": runtime_available,
        "count": len(result),
        "users": result,
    }


@app.get("/api/system")
async def api_system(session_token: str | None = Cookie(default=None)):
    if PASSWORD and not _check_session(session_token):
        raise HTTPException(status_code=401, detail="not authenticated")
    return _mock_system()


@app.get("/api/channels")
async def api_channels(session_token: str | None = Cookie(default=None)):
    if PASSWORD and not _check_session(session_token):
        raise HTTPException(status_code=401, detail="not authenticated")
    employees = await _corp_dir_users()
    if not employees:
        # fallback sample users
        employees = [
            {"email": "alice@example.com", "full_name": "Alice Ivanova"},
            {"email": "bob@example.com",   "full_name": "Bob Petrov"},
            {"email": "carol@example.com", "full_name": "Carol Sidorova"},
        ]
    return {"source": "sample", "channels": _mock_channels(employees)}


@app.get("/api/integrations")
async def api_integrations(session_token: str | None = Cookie(default=None)):
    if PASSWORD and not _check_session(session_token):
        raise HTTPException(status_code=401, detail="not authenticated")
    employees = await _corp_dir_users()
    if not employees:
        employees = [
            {"email": "alice@example.com", "full_name": "Alice Ivanova"},
            {"email": "bob@example.com",   "full_name": "Bob Petrov"},
            {"email": "carol@example.com", "full_name": "Carol Sidorova"},
        ]
    return {"source": "sample", "integrations": _mock_integrations(employees)}


@app.get("/api/audit")
async def api_audit(session_token: str | None = Cookie(default=None)):
    if PASSWORD and not _check_session(session_token):
        raise HTTPException(status_code=401, detail="not authenticated")
    return {"source": "sample", "records": _mock_audit()}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "admin-panel", "brand": BRAND}


# ---------------------------------------------------------------------------
# HTML — Login page
# ---------------------------------------------------------------------------

def _login_html(error_html: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BRAND} — Admin Login</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e8f0;
  display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#1a1f2e;border:1px solid #2d3748;border-radius:12px;
  padding:40px 48px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
h1{{font-size:1.4rem;font-weight:700;margin-bottom:6px;color:#fff}}
.sub{{font-size:.85rem;color:#718096;margin-bottom:28px}}
label{{display:block;font-size:.8rem;color:#a0aec0;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}}
input[type=password]{{width:100%;padding:10px 14px;background:#0f1117;border:1px solid #2d3748;
  border-radius:8px;color:#e2e8f0;font-size:.95rem;outline:none}}
input[type=password]:focus{{border-color:#4a90d9}}
button{{margin-top:18px;width:100%;padding:11px;background:#4a90d9;color:#fff;
  border:none;border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer}}
button:hover{{background:#357abd}}
.error{{color:#fc8181;font-size:.85rem;margin-top:12px;padding:10px;
  background:#2d1515;border-radius:6px;border:1px solid #7f1d1d}}
</style>
</head>
<body>
<div class="card">
  <h1>{BRAND} Admin</h1>
  <p class="sub">Оператор платформы</p>
  <form method="post" action="/login">
    <label for="password">Пароль</label>
    <input type="password" id="password" name="password" autofocus placeholder="••••••••">
    <button type="submit">Войти</button>
    {error_html}
  </form>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTML — Dashboard (single-page, inline CSS+JS, no external CDN)
# ---------------------------------------------------------------------------

def _dashboard_html() -> str:
    open_warning = ""
    if not PASSWORD:
        open_warning = """<div class="open-warning">
  ⚠ ADMIN_UI_PASSWORD не задан — панель открыта без авторизации. Задайте пароль перед развёртыванием.
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{BRAND} Admin</title>
<style>
/* ---- Reset & base ---- */
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,sans-serif;background:#0f1117;color:#e2e8f0;
  display:flex;min-height:100vh;font-size:14px}}

/* ---- Sidebar ---- */
.sidebar{{width:220px;min-height:100vh;background:#13172380;border-right:1px solid #1e2533;
  display:flex;flex-direction:column;flex-shrink:0;position:fixed;top:0;left:0;bottom:0}}
.sidebar-brand{{padding:20px 18px 14px;font-size:1.05rem;font-weight:700;color:#fff;
  border-bottom:1px solid #1e2533;letter-spacing:-.01em}}
.sidebar-brand span{{color:#4a90d9}}
.sidebar-nav{{flex:1;padding:10px 0}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:10px 18px;cursor:pointer;
  color:#a0aec0;font-size:.88rem;border-radius:0;transition:all .15s;user-select:none}}
.nav-item:hover{{background:#1e2533;color:#e2e8f0}}
.nav-item.active{{background:#1a2744;color:#60a5fa;font-weight:600}}
.nav-item.soon{{opacity:.45;cursor:not-allowed;font-style:italic}}
.nav-icon{{font-size:1rem;width:18px;text-align:center}}
.nav-label{{flex:1}}
.nav-badge{{font-size:.68rem;background:#1e2533;color:#718096;padding:2px 7px;
  border-radius:10px;border:1px solid #2d3748}}
.sidebar-footer{{padding:14px 18px;border-top:1px solid #1e2533}}
.logout-btn{{font-size:.8rem;color:#718096;text-decoration:none;cursor:pointer}}
.logout-btn:hover{{color:#fc8181}}

/* ---- Main ---- */
.main{{margin-left:220px;flex:1;display:flex;flex-direction:column;min-height:100vh}}
.topbar{{padding:14px 24px;border-bottom:1px solid #1e2533;display:flex;
  align-items:center;justify-content:space-between;background:#13172380}}
.topbar-title{{font-size:1rem;font-weight:600;color:#fff}}
.topbar-meta{{font-size:.78rem;color:#4a5568}}
.sample-badge{{display:inline-block;background:#2d2414;border:1px solid #7c5200;
  color:#d97706;border-radius:5px;padding:3px 9px;font-size:.72rem;font-weight:600;
  letter-spacing:.03em;margin-left:8px}}

.open-warning{{margin:14px 24px 0;padding:10px 14px;background:#2d1515;border:1px solid #7f1d1d;
  border-radius:7px;color:#fca5a5;font-size:.82rem}}

/* ---- Content ---- */
.content{{padding:20px 24px 40px;flex:1}}
.tab-panel{{display:none}}
.tab-panel.active{{display:block}}

/* ---- KPI cards ---- */
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:22px}}
.kpi{{background:#1a1f2e;border:1px solid #1e2533;border-radius:10px;padding:16px 20px}}
.kpi-label{{font-size:.75rem;color:#718096;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}}
.kpi-value{{font-size:1.7rem;font-weight:700;color:#fff;line-height:1}}
.kpi-sub{{font-size:.72rem;color:#4a5568;margin-top:5px}}
.kpi.ok .kpi-value{{color:#68d391}}
.kpi.warn .kpi-value{{color:#f6ad55}}
.kpi.info .kpi-value{{color:#60a5fa}}

/* ---- Section headers ---- */
.section-header{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.section-title{{font-size:.92rem;font-weight:600;color:#e2e8f0}}
.section-note{{font-size:.75rem;color:#718096}}

/* ---- Tables ---- */
.table-wrap{{overflow-x:auto;border-radius:9px;border:1px solid #1e2533;margin-bottom:22px}}
table{{width:100%;border-collapse:collapse;background:#1a1f2e}}
thead tr{{border-bottom:1px solid #1e2533}}
th{{padding:10px 14px;font-size:.75rem;font-weight:600;color:#718096;
  text-transform:uppercase;letter-spacing:.05em;text-align:left;white-space:nowrap}}
td{{padding:10px 14px;font-size:.83rem;color:#cbd5e0;border-bottom:1px solid #111827;
  white-space:nowrap}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#1e2533}}
.badge{{display:inline-block;padding:2px 8px;border-radius:5px;font-size:.72rem;font-weight:600}}
.badge-green{{background:#1a3a2a;color:#68d391;border:1px solid #276749}}
.badge-yellow{{background:#2d2414;color:#d97706;border:1px solid #7c5200}}
.badge-gray{{background:#1e2533;color:#718096;border:1px solid #2d3748}}
.badge-red{{background:#2d1515;color:#fc8181;border:1px solid #7f1d1d}}
.badge-blue{{background:#1a2744;color:#60a5fa;border:1px solid #1e3a6e}}
.na{{color:#4a5568;font-style:italic}}

/* ---- Loading / error ---- */
.loading{{color:#4a5568;padding:30px 0;text-align:center;font-style:italic}}
.err-msg{{color:#fc8181;padding:12px 16px;background:#2d1515;border-radius:7px;
  border:1px solid #7f1d1d;font-size:.82rem;margin:10px 0}}

/* ---- Audit ---- */
.audit-tag{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.68rem;
  background:#1e2533;color:#718096;border:1px solid #2d3748;margin:1px}}
.audit-outcome-allowed{{color:#68d391}}
.audit-outcome-denied{{color:#fc8181}}
.audit-outcome-pending{{color:#f6ad55}}
.audit-outcome-cancelled{{color:#718096}}

/* ---- System containers ---- */
.container-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-bottom:20px}}
.container-card{{background:#1e2533;border:1px solid #2d3748;border-radius:8px;padding:14px 16px}}
.container-name{{font-weight:600;color:#e2e8f0;font-size:.88rem;margin-bottom:4px}}
.container-image{{font-size:.75rem;color:#4a5568;font-family:monospace;margin-bottom:8px;
  overflow:hidden;text-overflow:ellipsis}}
.container-status{{font-size:.78rem}}

/* ---- Coming soon panels ---- */
.coming-soon{{background:#1a1f2e;border:1px dashed #2d3748;border-radius:10px;
  padding:60px 20px;text-align:center;color:#4a5568}}
.coming-soon h3{{color:#718096;margin-bottom:10px}}
.coming-soon p{{font-size:.83rem}}
.extend-hint{{margin-top:16px;display:inline-block;padding:8px 16px;background:#1e2533;
  border-radius:6px;border:1px solid #2d3748;color:#4a90d9;font-size:.8rem;font-family:monospace}}

/* ---- Scrollbar ---- */
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:#0f1117}}
::-webkit-scrollbar-thumb{{background:#2d3748;border-radius:3px}}
</style>
</head>
<body>

<!-- Sidebar -->
<aside class="sidebar">
  <div class="sidebar-brand"><span>{BRAND}</span> Admin</div>
  <nav class="sidebar-nav">
    <div class="nav-item active" onclick="showTab('users')" id="nav-users">
      <span class="nav-icon">👤</span>
      <span class="nav-label">Users</span>
    </div>
    <div class="nav-item" onclick="showTab('system')" id="nav-system">
      <span class="nav-icon">🖥</span>
      <span class="nav-label">System</span>
    </div>
    <div class="nav-item" onclick="showTab('channels')" id="nav-channels">
      <span class="nav-icon">💬</span>
      <span class="nav-label">Channels</span>
    </div>
    <div class="nav-item" onclick="showTab('integrations')" id="nav-integrations">
      <span class="nav-icon">🔌</span>
      <span class="nav-label">Integrations</span>
    </div>
    <div class="nav-item" onclick="showTab('audit')" id="nav-audit">
      <span class="nav-icon">🔍</span>
      <span class="nav-label">Audit</span>
    </div>
    <div style="height:1px;background:#1e2533;margin:10px 0"></div>
    <div class="nav-item soon" title="extend me — подключи Yandex 360 / Google Workspace">
      <span class="nav-icon">📁</span>
      <span class="nav-label">Files (extend me)</span>
      <span class="nav-badge">soon</span>
    </div>
    <div class="nav-item soon" title="extend me — подключи Kaiten / Jira / YouTrack">
      <span class="nav-icon">✅</span>
      <span class="nav-label">Tasks (extend me)</span>
      <span class="nav-badge">soon</span>
    </div>
    <div class="nav-item soon" title="extend me — добавь управление скиллами агентов">
      <span class="nav-icon">⚙</span>
      <span class="nav-label">Skills (extend me)</span>
      <span class="nav-badge">soon</span>
    </div>
    <div class="nav-item soon" title="extend me — настройки платформы, env, обновления">
      <span class="nav-icon">🛠</span>
      <span class="nav-label">Settings (extend me)</span>
      <span class="nav-badge">soon</span>
    </div>
  </nav>
  <div class="sidebar-footer">
    <a class="logout-btn" href="/logout">← Выйти</a>
  </div>
</aside>

<!-- Main -->
<main class="main">
  <header class="topbar">
    <div>
      <span class="topbar-title">{BRAND} — Operator Panel</span>
      <span class="sample-badge">SAMPLE DATA</span>
    </div>
    <div class="topbar-meta" id="topbar-time">загрузка...</div>
  </header>
  {open_warning}
  <div class="content">

    <!-- ===== USERS ===== -->
    <div class="tab-panel active" id="tab-users">
      <div class="kpi-row" id="users-kpi">
        <div class="kpi info"><div class="kpi-label">Сотрудников</div><div class="kpi-value" id="kpi-total">—</div><div class="kpi-sub">из corp-dir-broker</div></div>
        <div class="kpi ok"><div class="kpi-label">Активных</div><div class="kpi-value" id="kpi-active">—</div><div class="kpi-sub">статус: active (sample)</div></div>
        <div class="kpi warn"><div class="kpi-label">Idle</div><div class="kpi-value" id="kpi-idle">—</div><div class="kpi-sub">статус: idle (sample)</div></div>
        <div class="kpi"><div class="kpi-label">Runtime</div><div class="kpi-value" id="kpi-runtime">n/a</div><div class="kpi-sub">TODO: GET /runtimes</div></div>
      </div>
      <div class="section-header">
        <span class="section-title">Пользователи</span>
        <span class="section-note">identity — corp-dir-broker · метрики — sample</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Email</th><th>Имя</th><th>Должность</th><th>Отдел</th>
            <th>Статус</th><th>WebUI 7d</th><th>TG 7d</th><th>Storage</th>
            <th>Last seen</th><th>Runtime</th>
          </tr></thead>
          <tbody id="users-tbody"><tr><td colspan="10" class="loading">Загрузка...</td></tr></tbody>
        </table>
      </div>
    </div>

    <!-- ===== SYSTEM ===== -->
    <div class="tab-panel" id="tab-system">
      <div class="kpi-row" id="system-kpi">
        <div class="kpi info"><div class="kpi-label">Контейнеров</div><div class="kpi-value" id="kpi-containers">—</div><div class="kpi-sub">running / total (sample)</div></div>
        <div class="kpi ok"><div class="kpi-label">Диск</div><div class="kpi-value" id="kpi-disk">—</div><div class="kpi-sub">GB использовано (sample)</div></div>
        <div class="kpi info"><div class="kpi-label">MUX очередь</div><div class="kpi-value" id="kpi-mux">—</div><div class="kpi-sub">сообщений (sample)</div></div>
        <div class="kpi"><div class="kpi-label">Образ агента</div><div class="kpi-value" style="font-size:.8rem;padding-top:4px" id="kpi-image">—</div><div class="kpi-sub">HERMES_IMAGE</div></div>
      </div>
      <div class="section-header">
        <span class="section-title">Контейнеры</span>
        <span class="section-note">sample — замените на docker stats / Docker API</span>
      </div>
      <div class="container-grid" id="containers-grid"></div>
    </div>

    <!-- ===== CHANNELS ===== -->
    <div class="tab-panel" id="tab-channels">
      <div class="section-header">
        <span class="section-title">Активность по каналам</span>
        <span class="section-note">WebUI и Telegram per user — sample</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Email</th><th>Имя</th><th>WebUI сегодня</th><th>WebUI 7d</th>
            <th>TG сегодня</th><th>TG 7d</th><th>Последний канал</th>
          </tr></thead>
          <tbody id="channels-tbody"><tr><td colspan="7" class="loading">Загрузка...</td></tr></tbody>
        </table>
      </div>
    </div>

    <!-- ===== INTEGRATIONS ===== -->
    <div class="tab-panel" id="tab-integrations">
      <div class="section-header">
        <span class="section-title">Обращения к интеграциям (7d)</span>
        <span class="section-note">per user per broker — sample</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Email</th><th>Имя</th><th>Directory</th><th>Files</th>
            <th>Tasks</th><th>Memory</th><th>Onboarding</th>
          </tr></thead>
          <tbody id="integrations-tbody"><tr><td colspan="7" class="loading">Загрузка...</td></tr></tbody>
        </table>
      </div>
    </div>

    <!-- ===== AUDIT ===== -->
    <div class="tab-panel" id="tab-audit">
      <div class="section-header">
        <span class="section-title">Аудит-лог (последние записи)</span>
        <span class="section-note">sample — подключи audit-сервис (см. docs/AUDIT.md)</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Время</th><th>Тип события</th><th>Актор</th><th>Субъект</th>
            <th>Действие</th><th>Исход</th><th>Теги</th>
          </tr></thead>
          <tbody id="audit-tbody"><tr><td colspan="7" class="loading">Загрузка...</td></tr></tbody>
        </table>
      </div>
    </div>

  </div><!-- /content -->
</main>

<script>
// ---- Tab switching ----
const TABS = ['users','system','channels','integrations','audit'];
function showTab(name) {{
  TABS.forEach(t => {{
    document.getElementById('tab-'+t).classList.toggle('active', t===name);
    const n = document.getElementById('nav-'+t);
    if(n) n.classList.toggle('active', t===name);
  }});
  if(!loadedTabs.has(name)) {{ loadTab(name); loadedTabs.add(name); }}
}}

const loadedTabs = new Set(['users']);

// ---- Topbar clock ----
function updateClock() {{
  document.getElementById('topbar-time').textContent =
    new Date().toLocaleString('ru-RU', {{timeZone:'UTC',hour12:false}}) + ' UTC';
}}
updateClock(); setInterval(updateClock, 1000);

// ---- Helpers ----
function statusBadge(s) {{
  const map = {{active:'badge-green',idle:'badge-yellow',inactive:'badge-gray','n/a':'badge-gray'}};
  return `<span class="badge ${{map[s]||'badge-gray'}}">${{s||'—'}}</span>`;
}}
function outcomeBadge(o) {{
  return `<span class="audit-outcome-${{o}}">${{o}}</span>`;
}}
function relTime(iso) {{
  if(!iso) return '<span class="na">—</span>';
  const d = new Date(iso), now = Date.now(), diff = (now - d)/1000;
  if(diff<60) return Math.round(diff)+'с назад';
  if(diff<3600) return Math.round(diff/60)+'м назад';
  if(diff<86400) return Math.round(diff/3600)+'ч назад';
  return Math.round(diff/86400)+'д назад';
}}
function sampleNote(src) {{
  return src==='sample' ? '<span class="sample-badge">sample</span>' : '';
}}

async function fetchJSON(url) {{
  const r = await fetch(url);
  if(!r.ok) throw new Error(r.status);
  return r.json();
}}

function errRow(cols, msg) {{
  return `<tr><td colspan="${{cols}}" class="err-msg">${{msg}}</td></tr>`;
}}

// ---- Load tabs ----
async function loadTab(name) {{
  if(name==='users') await loadUsers();
  else if(name==='system') await loadSystem();
  else if(name==='channels') await loadChannels();
  else if(name==='integrations') await loadIntegrations();
  else if(name==='audit') await loadAudit();
}}

// Users
async function loadUsers() {{
  const tbody = document.getElementById('users-tbody');
  try {{
    const d = await fetchJSON('/api/users');
    document.getElementById('kpi-total').textContent = d.count;
    const active = d.users.filter(u=>u.status==='active').length;
    const idle = d.users.filter(u=>u.status==='idle').length;
    document.getElementById('kpi-active').textContent = active;
    document.getElementById('kpi-idle').textContent = idle;
    document.getElementById('kpi-runtime').textContent = d.runtime_available ? 'online' : 'n/a';
    tbody.innerHTML = d.users.map(u => `<tr>
      <td>${{u.email}}</td>
      <td>${{u.full_name||'—'}}</td>
      <td>${{u.position||'—'}}</td>
      <td>${{u.org_unit||'—'}}</td>
      <td>${{statusBadge(u.status)}}</td>
      <td>${{u.webui_7d}}</td>
      <td>${{u.tg_7d}}</td>
      <td>${{u.storage_mb}} MB</td>
      <td>${{relTime(u.last_seen)}}</td>
      <td><span class="na">${{u.runtime_status}}</span></td>
    </tr>`).join('');
  }} catch(e) {{
    tbody.innerHTML = errRow(10, 'Ошибка загрузки: '+e.message);
  }}
}}

// System
async function loadSystem() {{
  const grid = document.getElementById('containers-grid');
  try {{
    const d = await fetchJSON('/api/system');
    document.getElementById('kpi-containers').textContent = d.containers_running+' / '+d.containers_total;
    document.getElementById('kpi-disk').textContent = d.disk_used_gb+' / '+d.disk_total_gb;
    document.getElementById('kpi-mux').textContent = d.mux_queue_depth+' / '+d.mux_queue_max;
    document.getElementById('kpi-image').textContent = d.image;
    const statusCls = {{running:'badge-green',stopped:'badge-gray',exited:'badge-red'}};
    grid.innerHTML = (d.containers||[]).map(c => `
      <div class="container-card">
        <div class="container-name">${{c.name}}</div>
        <div class="container-image">${{c.image}}</div>
        <div class="container-status">
          <span class="badge ${{statusCls[c.status]||'badge-gray'}}">${{c.status}}</span>
          ${{c.port ? `<span style="color:#4a5568;font-size:.75rem;margin-left:8px">:${{c.port}}</span>`:''}}
        </div>
      </div>`).join('');
  }} catch(e) {{
    grid.innerHTML = '<div class="err-msg">Ошибка: '+e.message+'</div>';
  }}
}}

// Channels
async function loadChannels() {{
  const tbody = document.getElementById('channels-tbody');
  try {{
    const d = await fetchJSON('/api/channels');
    tbody.innerHTML = d.channels.map(c => `<tr>
      <td>${{c.email}}</td><td>${{c.full_name}}</td>
      <td>${{c.webui_today}}</td><td>${{c.webui_7d}}</td>
      <td>${{c.tg_today}}</td><td>${{c.tg_7d}}</td>
      <td>${{c.last_channel}}</td>
    </tr>`).join('');
  }} catch(e) {{
    tbody.innerHTML = errRow(7,'Ошибка: '+e.message);
  }}
}}

// Integrations
async function loadIntegrations() {{
  const tbody = document.getElementById('integrations-tbody');
  try {{
    const d = await fetchJSON('/api/integrations');
    tbody.innerHTML = d.integrations.map(i => `<tr>
      <td>${{i.email}}</td><td>${{i.full_name}}</td>
      <td>${{i.directory}}</td><td>${{i.files}}</td>
      <td>${{i.tasks}}</td><td>${{i.memory}}</td><td>${{i.onboarding}}</td>
    </tr>`).join('');
  }} catch(e) {{
    tbody.innerHTML = errRow(7,'Ошибка: '+e.message);
  }}
}}

// Audit
async function loadAudit() {{
  const tbody = document.getElementById('audit-tbody');
  try {{
    const d = await fetchJSON('/api/audit');
    tbody.innerHTML = d.records.map(r => `<tr>
      <td style="font-size:.75rem;color:#718096">${{relTime(r.ts)}}</td>
      <td style="font-family:monospace;font-size:.77rem">${{r.event_type}}</td>
      <td style="font-size:.78rem">${{r.actor?.id||'—'}}</td>
      <td style="font-size:.78rem">${{r.subject?.id||'—'}}</td>
      <td style="font-family:monospace;font-size:.77rem">${{r.action}}</td>
      <td>${{outcomeBadge(r.outcome)}}</td>
      <td>${{(r.tags||[]).map(t=>`<span class="audit-tag">${{t}}</span>`).join(' ')}}</td>
    </tr>`).join('');
  }} catch(e) {{
    tbody.innerHTML = errRow(7,'Ошибка: '+e.message);
  }}
}}

// Initial load
loadUsers();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point (for direct run / dev)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8655, reload=True)
