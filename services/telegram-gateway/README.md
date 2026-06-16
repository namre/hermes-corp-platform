# telegram-gateway (заглушка)

Шлюз между Telegram Bot API и платформой. Принимает webhook от Telegram,
аутентифицирует запрос, дедуплицирует обновления, резолвит пользователя
и форвардит сообщение в `identity-proxy`.

Порт: **8653**.

---

## Контракт

```
GET  /health
POST /telegram-webhook/{secret}
```

### POST /telegram-webhook/{secret}

Принимает JSON-тело Telegram Update. Возвращает `{"ok": true}` (Telegram
требует 200 в любом случае, иначе повторяет доставку).

Поведение:
- `secret` не совпадает с `TELEGRAM_WEBHOOK_SECRET` → **403** (fail-closed).
- `update_id` уже видели → тихое `{"ok": true, "note": "duplicate"}`.
- `tg_id` не найден в corp-dir-broker → тихое `{"ok": true}` без ответа пользователю.
- Текстовое сообщение от известного пользователя → форвард в identity-proxy.

---

## Переменные окружения

| Переменная | Обязательно | По умолчанию | Описание |
|---|---|---|---|
| `TELEGRAM_WEBHOOK_SECRET` | да | — | Секрет, задаётся при вызове `setWebhook` (`secret_token`). Хранить в `.env`, не в коде. |
| `CORP_DIR_URL` | нет | `http://corp-dir-broker:8652` | Адрес corp-dir-broker внутри docker-сети. |
| `PROXY_URL` | нет | `http://identity-proxy:8643` | Адрес identity-proxy. |
| `BROKER_INTERNAL_AUTH` | нет | — | Общий секрет для авторизации запросов к брокерам. |

В полной MUX-реализации добавляется:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Настоящий токен бота для отправки ответов (`sendMessage`). |
| `MUX_SECRET` | Мастер-секрет для HMAC-генерации per-user fake-токенов. |

---

## Место в MUX-архитектуре

В боевой системе **один бот обслуживает много пользователей** через MUX:

```
Telegram API
    │
    ▼
telegram-gateway   ← webhook-аутентификация, дедуп, резолв tg_id
    │
    ▼
identity-proxy     ← резолв личности → форвард в per-user runtime
    │
    ▼
MUX-прокси Bot API ← перехватывает setWebhook/getMe, passthrough остального
    │               ← per-runtime очереди ответов
    ▼
Telegram API       ← sendMessage от имени единого бота
```

Per-user fake-токен генерируется как `HMAC(runtime_id, MUX_SECRET)`. Это
позволяет каждому runtime «видеть» свой токен, не зная настоящего токена бота.
Подробнее — [docs/TELEGRAM_MUX.md](../../docs/TELEGRAM_MUX.md).

---

## Что реализовано / что ещё нужно

| Блок | Статус |
|---|---|
| Аутентификация секрета в пути webhook | реализовано |
| Дедупликация по update_id (in-memory) | реализовано (см. TODO про persistent store) |
| Резолв tg_id → сотрудник, fail-closed | реализовано |
| Форвард текста в identity-proxy | реализовано |
| Обратный sendMessage (ответ агента) | **TODO** |
| Typing-индикатор и реакции | **TODO** |
| Голос: STT → агент | **TODO** |
| Persistent watermark (Redis / БД) | **TODO** |
| Throttle неизвестных tg_id | **TODO** |
| chat_id ownership verification | **TODO** |

---

## Как зарегистрировать webhook

```bash
# TELEGRAM_WEBHOOK_SECRET — любая случайная строка, задаётся в .env
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://your-domain.example.com/telegram-webhook/<TELEGRAM_WEBHOOK_SECRET>" \
     -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Reverse-proxy (nginx/Caddy) с TLS выставляет этот path наружу. Сам сервис
слушает только внутри docker-сети (`127.0.0.1:8653`).
