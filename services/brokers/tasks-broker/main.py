"""tasks-broker — ЗАГЛУШКА таск-трекера.

Контракт:
  GET  /health
  GET  /tasks?assignee=<email>        -> {tasks: [...]}
  GET  /tasks/{task_id}               -> {...}
  POST /tasks/{task_id}/status        {status} -> {ok}

Заглушка отдаёт фейковые задачи из памяти. Реальная интеграция:
Kaiten / Jira / YouTrack / Asana. Перепишите доступ к данным, сохранив контракт.
"""
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="tasks-broker (stub)")
INTERNAL_AUTH = os.getenv("BROKER_INTERNAL_AUTH", "")

_TASKS = {
    "4945-22": {"id": "4945-22", "title": "РД по ЖК Заря", "assignee": "bob@example.com", "status": "in_progress"},
    "4945-31": {"id": "4945-31", "title": "Сравнить КП подрядчиков", "assignee": "bob@example.com", "status": "backlog"},
    "5001-7":  {"id": "5001-7",  "title": "Согласовать смету", "assignee": "alice@example.com", "status": "in_progress"},
}


def check_auth(h: str | None):
    if INTERNAL_AUTH and h != INTERNAL_AUTH:
        raise HTTPException(401, "bad internal auth")


class StatusReq(BaseModel):
    status: str


@app.get("/health")
def health():
    return {"status": "ok", "source": "stub", "tasks": len(_TASKS)}


@app.get("/tasks")
def list_tasks(assignee: str = "", x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    items = list(_TASKS.values())
    if assignee:
        items = [t for t in items if t["assignee"] == assignee.lower()]
    return {"tasks": items}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    if task_id not in _TASKS:
        raise HTTPException(404, "no such task")
    return _TASKS[task_id]


@app.post("/tasks/{task_id}/status")
def set_status(task_id: str, req: StatusReq, x_internal_auth: str | None = Header(None)):
    check_auth(x_internal_auth)
    if task_id not in _TASKS:
        raise HTTPException(404, "no such task")
    _TASKS[task_id]["status"] = req.status   # REPLACE: запись в реальный трекер
    return {"ok": True, "id": task_id, "status": req.status}
