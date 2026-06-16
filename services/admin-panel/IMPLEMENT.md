# IMPLEMENT.md — доведи admin-panel до боевого состояния

Это паста-промпт для LLM-ассистента. Вставь содержимое этого файла
вместе с текущим `services/admin-panel/main.py` и скажи ассистенту:
«Реализуй пункты ниже».

---

## Контекст

`services/admin-panel/main.py` — FastAPI-сервис (порт 8655), образец-заглушка
веб-панели оператора Hermes Corp Platform. Он уже работает: читает пользователей
из `corp-dir-broker GET /org-structure` и рисует дашборд. Остальные данные —
mock с пометкой `source: "sample"`.

Твоя задача — заменить mock на реальные данные (по одному пункту за раз
или все сразу — скажи явно).

---

## Где сейчас mock и что подключить

### 1. Метрики пользователей (webui_7d, tg_7d, storage, last_seen, status)

**Сейчас:** функция `_mock_metrics_for_user(email)` — детерминированный PRNG.

**Заменить на:**
- Если provisioner пишет лог в `registry.db` (SQLite): добавь модель
  `UserActivity` и читай оттуда через `aiosqlite`.
- Если используется audit-сервис: GET /api/audit?actor=<email>&limit=1
  для last_seen; агрегат по event_type для счётчиков.
- Если есть Loki: LogQL-запрос по контейнеру `hermes-u-<slug>`.
- Минимальная версия: provisioner добавляет GET /users/{email}/activity
  (последний запрос + счётчики).

### 2. Статус runtime (сейчас "n/a")

**Сейчас:** `_provisioner_runtimes()` проверяет `/health` и возвращает пустой список.
В `api_users` поле `runtime_status = "n/a"` с TODO-комментарием.

**Заменить на:**
- Добавь в `provisioner/main.py` эндпоинт `GET /runtimes` → список
  `[{"email": ..., "container": ..., "status": "running"|"stopped"|"exited"}]`.
- В `admin-panel/main.py`: убери TODO, вызови `GET /runtimes`, сопоставь
  по email, подставь реальный статус.

### 3. Системная информация (контейнеры, диск, MUX-очередь)

**Сейчас:** `_mock_system()` — хардкод.

**Заменить на:**
- Смонтируй `/var/run/docker.sock` в контейнер admin-panel (или используй
  отдельный sidecar).
- Используй `docker` Python SDK: `docker.from_env().containers.list(all=True)`
  для списка контейнеров и реального статуса.
- Диск: `shutil.disk_usage("/")` или вызов Docker API `/info`.
- MUX-очередь: если telegram-gateway имеет `/metrics` или `/queue/depth` —
  читай оттуда. Иначе — оставь mock с явным TODO.

### 4. Активность по каналам (WebUI / Telegram)

**Сейчас:** `_mock_channels(users)` — PRNG.

**Заменить на:**
- OpenWebUI пишет логи — парси docker logs `openwebui` | grep <email> или
  подключи к OpenWebUI БД (SQLite/PostgreSQL).
- Telegram-gateway: если пишет лог в файл или БД — аналогично.
- Loki/ELK: LogQL или Elasticsearch-запрос с group by user + by channel.

### 5. Обращения к интеграциям

**Сейчас:** `_mock_integrations(users)` — PRNG.

**Заменить на:**
- Audit-лог: фильтруй по event_type (`broker.files.*`, `broker.tasks.*` и т.д.)
  и считай по субъекту (email).
- Или: брокеры пишут счётчики в общий Redis — читай оттуда.

### 6. Аудит-лог (вкладка Audit)

**Сейчас:** `_mock_audit()` — 8 хардкоденных записей с правильной схемой из docs/AUDIT.md.

**Заменить на:**
- Создай `audit-service` (отдельный микросервис, append-only PostgreSQL
  или ClickHouse, контракт в docs/AUDIT.md).
- Добавь эндпоинт `GET /api/audit?limit=50&offset=0&event_type=&actor=`.
- В admin-panel: замени `_mock_audit()` на `httpx.AsyncClient().get(AUDIT_URL+"/records")`.
- Добавь env `AUDIT_SERVICE_URL`.

---

## Вкладки «extend me» (сейчас задизейблены)

### Files (Yandex 360 / Google Drive / S3)

- Добавь вкладку: список файлов per user (имя, размер, дата, владелец).
- Источник: `files-broker GET /files?user=<email>` (уже реализован в
  `services/brokers/files-broker/`).
- В sidebar: убери `soon` класс и `disabled` у nav-item.

### Tasks (Kaiten / Jira / YouTrack)

- Добавь вкладку: открытые задачи per user, статус, дедлайн.
- Источник: `tasks-broker GET /tasks?assignee=<email>`.

### Skills

- Вкладка управления корп-скиллами (список `company/skills/`, enable/disable
  per runtime, reload).
- Источник: provisioner API (нужно добавить эндпоинт).

### Settings

- Вкладка конфигурации платформы: env-параметры, обновление образа,
  список allowed_models, audit retention.
- Требует privileged-операций через provisioner + audit события.

---

## Авторизация (prod-upgrade)

Сейчас: in-memory set токенов (сбрасывается при рестарте, нет CSRF).

Заменить на:
- Подписанные JWT (PyJWT): `itsdangerous` или `python-jose`.
- Или OAuth2/OIDC (SSO через ваш провайдер) — используй `authlib`.
- CSRF-токен в форме логина.
- Rate limiting на `/login` (slowapi или nginx-level).

---

## Что НЕ менять

- Контракты `/api/*` эндпоинтов (структура ответа).
- Поле `"source": "sample"` — просто обнови значение на `"live"` когда
  данные станут реальными.
- Inline HTML/CSS/JS подход (без внешних CDN — требование шаблона).
- Порт 8655 и env-переменные (ADMIN_PANEL_BRAND, ADMIN_UI_PASSWORD и т.д.).
