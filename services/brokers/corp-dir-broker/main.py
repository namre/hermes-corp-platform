"""corp-dir-broker — ЗАГЛУШКА каталога сотрудников.

Контракт (стабилен — на него опирается identity-proxy):
  GET /health
  GET /users/by-email?email=<email>
  GET /users/by-telegram?id=<telegram_id>
  GET /users/search?q=<query>
  GET /org-structure

Заглушка читает sample_directory.json. Чтобы подключить РЕАЛЬНЫЙ источник
(HRIS / LDAP / Active Directory / HR-портал), перепишите только функцию
load_directory() и, при необходимости, поиск — эндпоинты и формат ответа
менять нельзя, иначе сломаете identity-proxy.
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query

app = FastAPI(title="corp-dir-broker (stub)")
INTERNAL_AUTH = os.getenv("BROKER_INTERNAL_AUTH", "")
DATA = Path(__file__).parent / "sample_directory.json"


def check_auth(x_internal_auth: str | None):
    # Брокер доступен только изнутри сети по общему секрету.
    if INTERNAL_AUTH and x_internal_auth != INTERNAL_AUTH:
        raise HTTPException(status_code=401, detail="bad internal auth")


def load_directory() -> list[dict]:
    # REPLACE: здесь подключаете свой источник правды о сотрудниках.
    # Сейчас — локальный JSON. В проде это был HTTP-запрос к HR-API с кэшем.
    return json.loads(DATA.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    return {"status": "ok", "source": "stub", "count": len(load_directory())}


@app.get("/users/by-email")
def by_email(email: str = Query(...), x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    email = email.strip().lower()
    for u in load_directory():
        if u["email"].lower() == email:
            return u
    raise HTTPException(404, "not found")


@app.get("/users/by-telegram")
def by_telegram(id: str = Query(...), x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    for u in load_directory():
        if str(u.get("telegram_id")) == str(id):
            return u
    raise HTTPException(404, "not found")


@app.get("/users/search")
def search(q: str = Query(...), x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    q = q.strip().lower()
    hits = [
        u for u in load_directory()
        if q in u["full_name"].lower() or q in u["position"].lower()
    ]
    return {"query": q, "results": hits}


@app.get("/org-structure")
def org_structure(x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    return {"employees": load_directory()}
