"""telegram-gateway — ЗАГЛУШКА Telegram-шлюза платформы.

Задача: принять webhook от Telegram Bot API, проверить подлинность запроса,
задедуплицировать update, резолвить tg_id → сотрудника через corp-dir-broker
и переслать сообщение в identity-proxy как запрос к агенту.

Это ЗАГЛУШКА с рабочим скелетом:
  - аутентификация webhook реализована (secret в пути + fail-closed),
  - дедупликация по update_id реализована (in-memory; TODO: persistent store),
  - резолв и форвард реализованы,
  - обратная отправка (sendMessage), typing-loop и реакции помечены TODO.

Порт: 8653.

Поток:
  Telegram Bot API  ──► POST /telegram-webhook/{secret}
        │ 1. проверка secret
        │ 2. дедуп по update_id (in-memory watermark)
        │ 3. резолв tg_id → email через corp-dir-broker
        │    fail-closed: неизвестный tg_id → 200 OK (тихий отказ)
        └─► 4. форвард в identity-proxy POST /v1/chat/completions
                  заголовок: X-Telegram-Id: <tg_id>
              (TODO: 5. отправить ответ обратно sendMessage)
"""
import os
import hmac
import hashlib
import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

TELEGRAM_WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
CORP_DIR_URL: str = os.getenv("CORP_DIR_URL", "http://corp-dir-broker:8652")
PROXY_URL: str = os.getenv("PROXY_URL", "http://identity-proxy:8643")
INTERNAL_AUTH: str = os.getenv("BROKER_INTERNAL_AUTH", "")

# MUX_SECRET используется для генерации per-user fake-токенов в полной реализации
# MUX_SECRET: str = os.getenv("MUX_SECRET", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-gateway")

app = FastAPI(title="telegram-gateway (stub)")

# ---------------------------------------------------------------------------
# Дедупликация update_id — in-memory watermark.
#
# TODO(REPLACE): заменить на persistent store (Redis / БД) — при рестарте
# сервиса in-memory set сбрасывается, и в окне перезапуска Telegram повторно
# доставит накопившиеся updates. В проде хранится last_seen_update_id
# (монотонно возрастающий) в персистентном хранилище; достаточно хранить
# одно число, не весь набор видов update_id.
# ---------------------------------------------------------------------------
_SEEN_UPDATE_IDS: set[int] = set()


def _is_duplicate(update_id: int) -> bool:
    """Вернуть True, если update_id уже обрабатывался (дедуп)."""
    if update_id in _SEEN_UPDATE_IDS:
        return True
    _SEEN_UPDATE_IDS.add(update_id)
    # Ограничиваем размер in-memory set (скользящее окно).
    # В persistent-варианте достаточно хранить max(update_id).
    if len(_SEEN_UPDATE_IDS) > 10_000:
        _SEEN_UPDATE_IDS.clear()
    return False


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _check_secret(secret: str) -> None:
    """Проверить секрет из пути webhook. Fail-closed: 403 при несовпадении."""
    if not TELEGRAM_WEBHOOK_SECRET:
        # Защита: если секрет не задан в env — отказывать всем.
        raise HTTPException(status_code=403, detail="webhook secret not configured")
    if not hmac.compare_digest(secret, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="invalid webhook secret")


async def _resolve_tg_user(tg_id: str) -> dict | None:
    """Резолвить Telegram ID в запись сотрудника через corp-dir-broker.

    Возвращает dict сотрудника или None если неизвестен.
    Fail-closed: None вынуждает вызывающий код тихо отказать.
    """
    headers = {"x-internal-auth": INTERNAL_AUTH}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(
                f"{CORP_DIR_URL}/users/by-telegram",
                params={"id": tg_id},
                headers=headers,
            )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as exc:
        log.warning("corp-dir-broker недоступен при резолве tg_id=%s: %s", tg_id, exc)
        return None


async def _forward_to_proxy(tg_id: str, text: str) -> dict:
    """Переслать сообщение в identity-proxy как /v1/chat/completions."""
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": text}],
    }
    headers = {
        "Content-Type": "application/json",
        "X-Telegram-Id": tg_id,
    }
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{PROXY_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "telegram-gateway"}


@app.post("/telegram-webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> JSONResponse:
    """Приём обновлений от Telegram Bot API.

    Telegram требует возврата 200 OK быстро — тяжёлую обработку нужно
    выносить в фоновую задачу (TODO: BackgroundTasks или очередь).
    """
    # 1. Проверка секрета в пути (аутентификация webhook).
    #    Секрет задаётся при вызове setWebhook: ?secret_token=<TELEGRAM_WEBHOOK_SECRET>
    #    Telegram передаёт его в заголовке X-Telegram-Bot-Api-Secret-Token,
    #    но надёжнее держать его частью URL пути — так он не попадает в логи
    #    reverse-proxy по умолчанию и не зависит от реализации заголовков.
    _check_secret(secret)

    body = await request.json()
    update_id: int | None = body.get("update_id")

    # 2. Дедупликация по update_id.
    if update_id is not None and _is_duplicate(update_id):
        log.info("Дубликат update_id=%s — пропускаем", update_id)
        return JSONResponse({"ok": True, "note": "duplicate"})

    message = body.get("message") or body.get("edited_message")
    if not message:
        # Не текстовый update (callback_query, inline и т.д.) — пропускаем.
        # TODO: расширить под другие типы updates по необходимости.
        return JSONResponse({"ok": True})

    tg_id = str(message.get("from", {}).get("id", ""))
    chat_id = message.get("chat", {}).get("id")
    text: str = message.get("text", "").strip()

    if not tg_id or not chat_id:
        return JSONResponse({"ok": True})

    # TODO: typing-индикатор — sendChatAction(chat_id, "typing") в цикле
    # пока агент обрабатывает запрос. Останавливать по завершении.

    # TODO: реакция на входящее сообщение (например, 🤔 через setMessageReaction),
    # снять реакцию после получения ответа агента.

    # 3. Резолв tg_id → сотрудник (fail-closed).
    #    Дополнительно следует проверить chat_id ownership: убедиться, что
    #    chat_id в update совпадает с chat_id, зарегистрированным за этим tg_id
    #    в каталоге — так предотвращается спуфинг chat_id.
    user = await _resolve_tg_user(tg_id)
    if user is None:
        log.warning(
            "Неизвестный tg_id=%s (chat_id=%s) — fail-closed, запрос отклонён "
            "(throttle/silence; НЕ возвращать подробную ошибку в Telegram).",
            tg_id, chat_id,
        )
        # Возвращаем Telegram 200 OK, чтобы не получать повторных попыток,
        # но НЕ отвечаем пользователю — тихий отказ.
        # TODO: после N попыток от неизвестного tg_id — throttle/временный ban.
        return JSONResponse({"ok": True})

    if not text:
        # Голосовое сообщение или медиа без подписи.
        # TODO(VOICE): входящий voice (.oga/opus) → скачать файл через
        #   getFile → STT (faster-whisper локально или внешний провайдер) →
        #   транскрипт передать агенту вместе с путём к исходному файлу.
        # TODO(MEDIA): фото/документ → переслать в files-broker или в data-том runtime.
        return JSONResponse({"ok": True})

    # 4. Форвард в identity-proxy.
    try:
        result = await _forward_to_proxy(tg_id=tg_id, text=text)
        log.info("Ответ от proxy для tg_id=%s: %s", tg_id, result)
    except Exception as exc:
        log.error("Ошибка форварда в proxy для tg_id=%s: %s", tg_id, exc)
        # TODO: отправить пользователю сообщение об ошибке через sendMessage.
        return JSONResponse({"ok": True, "error": "proxy_unavailable"})

    # 5. TODO(REPLY): отправить ответ агента обратно в Telegram.
    #    Ответ агента лежит в result["choices"][0]["message"]["content"].
    #    Нужно:
    #      a) достать текст ответа;
    #      b) разбить на чанки по 4096 символов (лимит Telegram);
    #      c) вызвать Bot API sendMessage для каждого чанка:
    #           POST https://api.telegram.org/bot<TOKEN>/sendMessage
    #           {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
    #    Токен бота в MUX-архитектуре — per-user fake-токен (HMAC(runtime_id,
    #    MUX_SECRET)); MUX в proxy перехватывает глобальные Bot API методы
    #    (setWebhook, getMe) и passthrough остальные. Здесь используется
    #    real_bot_token из env (переменная TELEGRAM_BOT_TOKEN), но в полной
    #    реализации MUX шлёт через единый глобальный токен с per-runtime очередями.
    #
    #    Пример (закомментирован — требует TELEGRAM_BOT_TOKEN и раскоммента):
    #
    # TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # agent_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    # if agent_text and TELEGRAM_BOT_TOKEN:
    #     chunks = [agent_text[i:i+4096] for i in range(0, len(agent_text), 4096)]
    #     async with httpx.AsyncClient(timeout=30) as c:
    #         for chunk in chunks:
    #             await c.post(
    #                 f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
    #                 json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
    #             )

    return JSONResponse({"ok": True})
