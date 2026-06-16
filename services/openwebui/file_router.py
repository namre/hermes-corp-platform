"""
title: Corp File Router
author: hermes-corp-platform
description: Обработка файлов между OpenWebUI и агентом. ВХОД — вложения форвардятся
    в identity-proxy /v1/files (бинарь читается прямо из хранилища OpenWebUI),
    чтобы они оказались в data-папке персонального runtime. ВЫХОД — в ответе агента
    ищутся абсолютные пути (напр. /opt/data/report.xlsx) и заменяются на ссылки
    для скачивания. Устанавливается как Function (Filter) в OpenWebUI.
version: 1.0.0
required_open_webui_version: 0.4.0

ОБРАЗЕЦ. Секретов нет: URL и ключ задаются «вентилями» (Valves) в админке
OpenWebUI. По умолчанию указывает на internal identity-proxy.
"""
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

# Нативный доступ к файлам OpenWebUI (если доступен внутри образа)
try:
    from open_webui.models.files import Files as _OWUIFiles
except Exception:
    _OWUIFiles = None
try:
    from open_webui.config import UPLOAD_DIR as _OWUI_UPLOAD_DIR
except Exception:
    _OWUI_UPLOAD_DIR = "/app/backend/data/uploads"

# Абсолютные пути, которые агент может вернуть как «вот ваш файл».
_PATH_RE = re.compile(
    r"(?P<path>/(?:opt/data|workspace)/[^\s\"'`<>)\]]+\.[A-Za-z0-9]{1,8})",
    re.IGNORECASE,
)


class Filter:
    class Valves(BaseModel):
        # REPLACE при необходимости; по умолчанию — internal proxy.
        proxy_files_url: str = Field(
            default="http://identity-proxy:8643/v1/files",
            description="Эндпоинт загрузки файла в proxy",
        )
        proxy_register_url: str = Field(
            default="http://identity-proxy:8643/v1/files/register-existing",
            description="Регистрация файла, уже лежащего в data-папке runtime",
        )
        proxy_download_base: str = Field(
            default="http://identity-proxy:8643/v1/files",
            description="База для ссылок скачивания: /<file_id>/content?... ",
        )
        client_api_key: str = Field(
            default="",
            description="Bearer для proxy (HERMES_API_KEY). Задаётся в админке, не в коде.",
        )
        materialize_outputs: bool = Field(default=True)
        emit_status: bool = Field(default=True)
        enabled: bool = Field(default=True)

    def __init__(self):
        self.valves = self.Valves()

    # ---------- helpers ----------
    def _headers(self, email: Optional[str]) -> Dict[str, str]:
        h = {}
        if self.valves.client_api_key:
            h["Authorization"] = f"Bearer {self.valves.client_api_key}"
        if email:
            h["X-OpenWebUI-User-Email"] = email   # личность для proxy
        return h

    async def _emit(self, emitter, text: str, done: bool = False):
        if emitter and self.valves.emit_status:
            await emitter({"type": "status", "data": {"description": text, "done": done}})

    def _read_binary(self, file_id: str) -> Optional[bytes]:
        """Достаём бинарь файла из хранилища OpenWebUI по file_id."""
        if _OWUIFiles is not None:
            try:
                fmodel = _OWUIFiles.get_file_by_id(file_id)
                path = getattr(fmodel, "path", None) or getattr(fmodel, "meta", {}).get("path")
                if path and os.path.isfile(path):
                    return open(path, "rb").read()
            except Exception:
                pass
        # Фолбэк: ищем по file_id в каталоге загрузок.
        if os.path.isdir(_OWUI_UPLOAD_DIR):
            for fname in os.listdir(_OWUI_UPLOAD_DIR):
                if file_id in fname:
                    return open(os.path.join(_OWUI_UPLOAD_DIR, fname), "rb").read()
        return None

    def _download_url(self, file_id: str, filename: str, email: str) -> str:
        q = urlencode({"key": self.valves.client_api_key, "email": email, "name": filename})
        return f"{self.valves.proxy_download_base}/{file_id}/content?{q}"

    # ---------- INPUT: вложения → runtime ----------
    async def inlet(self, body: Dict[str, Any], __user__: Optional[dict] = None,
                    __event_emitter__=None) -> Dict[str, Any]:
        if not self.valves.enabled:
            return body
        files: List[dict] = body.get("files") or body.get("metadata", {}).get("files") or []
        if not files:
            return body
        email = (__user__ or {}).get("email", "")
        await self._emit(__event_emitter__, f"📤 Передаю {len(files)} файл(ов) в runtime…")
        async with httpx.AsyncClient(timeout=60) as c:
            for f in files:
                raw = f.get("file", f)
                file_id = raw.get("id")
                fname = raw.get("filename") or raw.get("name") or file_id
                binary = self._read_binary(file_id) if file_id else None
                if not binary:
                    continue
                try:
                    await c.post(self.valves.proxy_files_url,
                                 headers=self._headers(email),
                                 files={"file": (fname, binary)})
                except Exception:
                    pass
        await self._emit(__event_emitter__, "✅ Файлы переданы, агент начинает обработку…", done=True)
        return body

    # ---------- OUTPUT: пути в ответе → ссылки ----------
    async def outlet(self, body: Dict[str, Any], __user__: Optional[dict] = None,
                     __event_emitter__=None) -> Dict[str, Any]:
        if not (self.valves.enabled and self.valves.materialize_outputs):
            return body
        email = (__user__ or {}).get("email", "")
        msgs = body.get("messages", [])
        if not msgs:
            return body
        content = msgs[-1].get("content", "")
        if not isinstance(content, str):
            return body
        paths = list({m.group("path") for m in _PATH_RE.finditer(content)})
        if not paths:
            return body
        async with httpx.AsyncClient(timeout=30) as c:
            for path in paths:
                filename = os.path.basename(path)
                try:
                    r = await c.post(self.valves.proxy_register_url,
                                     headers=self._headers(email),
                                     json={"path": path, "email": email})
                    info = r.json()
                    file_id = info["id"]
                    url = info.get("download_url") or self._download_url(file_id, filename, email)
                    content = content.replace(path, f"[{filename}]({url})")
                except Exception:
                    pass
        msgs[-1]["content"] = content
        return body
