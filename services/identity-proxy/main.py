"""identity-proxy — точка входа платформы.

Задача: понять, КТО пришёл, найти/поднять ЕГО персональный runtime и
переслать запрос туда. Плюс — два защитных контура: детектор подозрительных
паттернов и (на стороне provisioner) срезание секретов платформы.

Это СКЕЛЕТ: маршрутизация и резолв личности реализованы, фактический форвард
в runtime помечен TODO под ваш транспорт к Hermes-Agent.

Поток:
  внешний канал (Telegram/Web) ──► identity-proxy
        │ 1. кто это?  → corp-dir-broker (by-telegram / by-email)
        │ 2. есть ли runtime?  → provisioner /runtimes/ensure
        │ 3. security_detect(текст)
        └─► 4. forward в http://<runtime>/v1/chat/completions
"""
import os
import re
import httpx
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="identity-proxy")

CORP_DIR_URL = os.getenv("CORP_DIR_URL", "http://corp-dir-broker:8652")
PROVISIONER_URL = os.getenv("PROVISIONER_URL", "http://provisioner:8650")
INTERNAL_AUTH = os.getenv("BROKER_INTERNAL_AUTH", "")
DETECT = os.getenv("SECURITY_DETECTION_ENABLED", "true").lower() == "true"
BLOCK = os.getenv("SECURITY_BLOCK_ON_DETECTION", "true").lower() == "true"

# Грубые паттерны вытягивания секретов / джейлбрейка. В проде — отдельный,
# постоянно дополняемый детектор. Здесь — наглядный минимум.
SUSPICIOUS = [
    re.compile(r"ignore (all|previous) instructions", re.I),
    re.compile(r"(выгрузи|покажи).{0,20}(все )?(парол|секрет|токен|api[ _-]?key)", re.I),
    re.compile(r"system prompt", re.I),
]


def security_detect(text: str) -> list[str]:
    if not DETECT or not text:
        return []
    return [p.pattern for p in SUSPICIOUS if p.search(text)]


async def resolve_user(telegram_id: str | None, email: str | None) -> dict:
    headers = {"x-internal-auth": INTERNAL_AUTH}
    async with httpx.AsyncClient(timeout=5) as c:
        if telegram_id:
            r = await c.get(f"{CORP_DIR_URL}/users/by-telegram", params={"id": telegram_id}, headers=headers)
        elif email:
            r = await c.get(f"{CORP_DIR_URL}/users/by-email", params={"email": email}, headers=headers)
        else:
            raise HTTPException(401, "no identity provided")
    if r.status_code != 200:
        raise HTTPException(403, "user not in corporate directory")
    return r.json()


async def ensure_runtime(user_email: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{PROVISIONER_URL}/runtimes/ensure",
                         json={"user": user_email},
                         headers={"x-internal-auth": INTERNAL_AUTH})
    if r.status_code != 200:
        raise HTTPException(502, "provisioner failed")
    return r.json()["endpoint"]   # напр. http://hermes-u-alice:8642


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat(request: Request,
               x_telegram_id: str | None = Header(None),
               x_user_email: str | None = Header(None),
               # OpenWebUI с ENABLE_FORWARD_USER_INFO_HEADERS=true шлёт email
               # вошедшего пользователя этим заголовком — так резолвится веб-личность.
               x_openwebui_user_email: str | None = Header(None)):
    body = await request.json()
    text = " ".join(m.get("content", "") for m in body.get("messages", []) if isinstance(m.get("content"), str))

    hits = security_detect(text)
    if hits and BLOCK:
        raise HTTPException(400, {"blocked": True, "reason": "suspicious_patterns", "patterns": hits})

    email = x_user_email or x_openwebui_user_email
    user = await resolve_user(x_telegram_id, email)
    endpoint = await ensure_runtime(user["email"])

    # TODO(REPLACE): форвард запроса в персональный runtime пользователя.
    # async with httpx.AsyncClient(timeout=120) as c:
    #     r = await c.post(f"{endpoint}/v1/chat/completions", json=body,
    #                      headers={"Authorization": f"Bearer {os.getenv('HERMES_API_KEY')}"})
    #     return r.json()
    return {
        "note": "SKELETON: routing resolved, wire up the forward to enable.",
        "resolved_user": user["email"],
        "runtime_endpoint": endpoint,
        "security_warning": hits or None,
    }


# ======================================================================
# Файловый слой (контракт для OpenWebUI File Router).
# ВХОД: вложения из чата складываются в data-папку runtime пользователя.
# ВЫХОД: файлы, созданные агентом (/opt/data/...), регистрируются и отдаются
# по ссылке для скачивания. Здесь — рабочая ЗАГЛУШКА (in-memory); в проде
# файлы пишутся/читаются в томе персонального runtime пользователя.
# ======================================================================
import uuid
from fastapi import UploadFile, File as FastFile
from fastapi.responses import Response

_FILES: dict[str, dict] = {}   # file_id -> {filename, content, owner}


@app.post("/v1/files")
async def upload_file(file: UploadFile = FastFile(...),
                      x_openwebui_user_email: str | None = Header(None)):
    """Приём вложения от OpenWebUI File Router → в runtime пользователя."""
    data = await file.read()
    fid = uuid.uuid4().hex[:12]
    # REPLACE: записать data в data-том runtime пользователя (по email).
    _FILES[fid] = {"filename": file.filename, "content": data, "owner": x_openwebui_user_email}
    return {"id": fid, "filename": file.filename}


@app.post("/v1/files/register-existing")
async def register_existing(body: dict,
                            x_openwebui_user_email: str | None = Header(None)):
    """Регистрация файла, который агент уже создал в своей data-папке."""
    path = body.get("path", "")
    fid = uuid.uuid4().hex[:12]
    # REPLACE: прочитать файл по path из тома runtime пользователя.
    _FILES[fid] = {"filename": path.split("/")[-1], "content": b"", "owner": x_openwebui_user_email,
                   "path": path}
    return {"id": fid, "download_url": f"/v1/files/{fid}/content"}


@app.get("/v1/files/{file_id}/content")
async def download_file(file_id: str):
    """Отдать файл по ссылке (её подставляет File Router в ответ агента)."""
    f = _FILES.get(file_id)
    if not f:
        raise HTTPException(404, "no such file")
    return Response(content=f["content"],
                    media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{f["filename"]}"'})
