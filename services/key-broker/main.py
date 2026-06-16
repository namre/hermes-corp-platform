"""key-broker — изоляция per-user LLM-ключей.

Каждому пользователю — свой виртуальный ключ к LLM-шлюзу. Платформенный
ключ (LITELLM_MASTER_KEY или аналог) не попадает в user-runtime ни в каком
виде. Вместо него runtime получает short-lived или постоянный virtual key,
выданный key-broker-ом и ограниченный лимитами этого пользователя.

Заглушка: ключ генерируется детерминированно через HMAC(user_id, system_secret)
и кэшируется в памяти процесса. В продакшне замените на PostgreSQL + pgcrypto
или интеграцию с LiteLLM /key/generate (см. IMPLEMENT.md).

Порт: 8700.
"""
import hmac
import hashlib
import os
import time
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="key-broker")

SYSTEM_SECRET = os.getenv("KEYBROKER_SYSTEM_SECRET", "")

# Кэш: user_id -> {"key": str, "created_at": float}
# В продакшне замените на PostgreSQL (см. IMPLEMENT.md).
_key_cache: dict[str, dict] = {}


def _check_bearer(authorization: str | None) -> None:
    """Проверяем Authorization: Bearer <KEYBROKER_SYSTEM_SECRET>.

    401 при любом несовпадении — включая пустой заголовок.
    """
    if not SYSTEM_SECRET:
        # Если секрет не задан — сервис запущен без защиты (только для dev).
        return
    expected = f"Bearer {SYSTEM_SECRET}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid system secret")


def _generate_key(user_id: str) -> str:
    """Детерминированный virtual key: HMAC-SHA256(user_id, SYSTEM_SECRET).

    Формат: vk-<hex32> — легко отличим от платформенного мастер-ключа.
    Детерминированность важна для идемпотентности без персистентности.
    REPLACE: в продакшне генерируйте случайный ключ и храните в БД
    (см. IMPLEMENT.md — postgres + pgcrypto или LiteLLM /key/generate).
    """
    secret = SYSTEM_SECRET.encode() if SYSTEM_SECRET else b"dev-insecure"
    digest = hmac.new(secret, user_id.encode(), hashlib.sha256).hexdigest()
    return f"vk-{digest[:32]}"


class KeyRequest(BaseModel):
    user_id: str   # email или внутренний идентификатор пользователя


@app.get("/health")
def health():
    return {"status": "ok", "backend": "stub-hmac", "cached_users": len(_key_cache)}


@app.post("/v1/keys")
def get_or_create_key(
    req: KeyRequest,
    authorization: str | None = Header(None),
):
    """Выдать (или вернуть кэшированный) virtual key для пользователя.

    Запрос только от provisioner или другого доверенного компонента платформы:
      Authorization: Bearer <KEYBROKER_SYSTEM_SECRET>
      {"user_id": "alice@example.com"}

    Ответ:
      {"key": "vk-<hex>", "user_id": "...", "source": "cache|generated"}
    """
    _check_bearer(authorization)
    uid = req.user_id.strip().lower()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required")

    if uid in _key_cache:
        return {"key": _key_cache[uid]["key"], "user_id": uid, "source": "cache"}

    key = _generate_key(uid)
    _key_cache[uid] = {"key": key, "created_at": time.time()}
    return {"key": key, "user_id": uid, "source": "generated"}
