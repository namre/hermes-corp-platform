"""files-broker — ЗАГЛУШКА облачного хранилища пользователя.

Контракт:
  GET  /health
  POST /files/upload            {user, filename, content_b64} -> {file_id}
  POST /files/{file_id}/link    {user} -> {public_url}
  GET  /calendar/freebusy?user=&date=  -> {busy: bool, next_slot}

Заглушка хранит всё в памяти и выдаёт фейковые ссылки. Реальная интеграция:
Yandex 360 / Google Drive / SharePoint / S3. Важная деталь из боевого опыта:
файлы кладите в облако САМОГО пользователя (от его OAuth-токена), а не в общий
бакет платформы — тогда сотрудник видит всё, что отправлял, у себя на диске,
и платформа не становится файловой системой.
"""
import os
import uuid
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="files-broker (stub)")
INTERNAL_AUTH = os.getenv("BROKER_INTERNAL_AUTH", "")
_STORE: dict[str, dict] = {}


def check_auth(h: str | None):
    if INTERNAL_AUTH and h != INTERNAL_AUTH:
        raise HTTPException(401, "bad internal auth")


class UploadReq(BaseModel):
    user: str
    filename: str
    content_b64: str = ""


class LinkReq(BaseModel):
    user: str


@app.get("/health")
def health():
    return {"status": "ok", "source": "stub", "files": len(_STORE)}


@app.post("/files/upload")
def upload(req: UploadReq, x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    fid = uuid.uuid4().hex[:12]
    _STORE[fid] = {"user": req.user, "filename": req.filename}
    return {"file_id": fid, "filename": req.filename}


@app.post("/files/{file_id}/link")
def make_link(file_id: str, req: LinkReq, x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    if file_id not in _STORE:
        raise HTTPException(404, "no such file")
    # REPLACE: реальный публичный шэр из облака пользователя.
    return {"public_url": f"https://files.example.invalid/s/{file_id}"}


@app.get("/calendar/freebusy")
def freebusy(user: str, date: str = "", x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    # REPLACE: запрос к календарю пользователя. Заглушка всегда «свободен».
    return {"user": user, "busy": False, "next_slot": None}
