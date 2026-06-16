# admin-panel

Веб-панель оператора Hermes Corp Platform. Образец-заглушка: рабочая,
читает пользователей из corp-dir-broker, остальные данные — правдоподобные
mock-данные, помеченные `source: "sample"`. Порт: **8655**.

## Вкладки

| Вкладка | Данные | Источник |
|---|---|---|
| **Users** | Список сотрудников (email, имя, должность, отдел), метрики активности, статус runtime | identity — corp-dir-broker; метрики — sample |
| **System** | Образ агента, счётчики контейнеров, диск, MUX-очередь, карточки контейнеров | sample (TODO: docker stats / Docker API) |
| **Channels** | Активность WebUI и Telegram per user за сегодня и 7 дней | sample |
| **Integrations** | Обращения к брокерам per user: Directory / Files / Tasks / Memory / Onboarding | sample |
| **Audit** | Последние записи аудита (event_type, актор, субъект, действие, исход, теги) | sample (TODO: audit-сервис) |
| Files / Tasks / Skills / Settings | Disabled — помечены «extend me» | — |

Все вкладки со статусом «extend me» — точки расширения: подключи реальные
данные из соответствующих брокеров и сервисов (см. IMPLEMENT.md).

## Данные: что реальное, что mock

| Данные | Откуда | Пометка |
|---|---|---|
| Список пользователей (email, имя, должность, отдел) | `corp-dir-broker GET /org-structure` | `source_users: "corp-dir-broker"` |
| Статус runtime пользователя | TODO: `provisioner GET /runtimes` не реализован | `runtime_status: "n/a"` |
| Метрики активности (webui_7d, tg_7d, storage, last_seen, status) | mock (детерминированный PRNG от email) | `source: "sample"` |
| Системная информация (контейнеры, диск, MUX) | mock | `source: "sample"` |
| Активность каналов per user | mock | `source: "sample"` |
| Обращения к интеграциям per user | mock | `source: "sample"` |
| Аудит-лог | mock (структура соответствует docs/AUDIT.md) | `source: "sample"` |

## Env-переменные

| Переменная | По умолчанию | Описание |
|---|---|---|
| `ADMIN_PANEL_BRAND` | `Corp AI` | Название в шапке и заголовке |
| `ADMIN_UI_PASSWORD` | _(пусто — открытый доступ)_ | Пароль для входа. Если пусто — панель открыта с предупреждением |
| `CORP_DIR_URL` | `http://corp-dir-broker:8652` | URL corp-dir-broker |
| `PROVISIONER_URL` | `http://provisioner:8650` | URL provisioner |
| `BROKER_INTERNAL_AUTH` | _(пусто)_ | Общий секрет `x-internal-auth` для брокеров |
| `HERMES_IMAGE` | `your-registry/hermes-agent:latest` | Образ агента для отображения в System |

## Быстрый старт

```bash
# Dev (без Docker, нужен Python 3.12+)
cd services/admin-panel
pip install -r requirements.txt
ADMIN_PANEL_BRAND="My Corp" CORP_DIR_URL=http://localhost:8652 \
  uvicorn main:app --port 8655 --reload
# → http://localhost:8655

# Через docker-compose (добавь сервис в docker-compose.yml — см. ниже)
docker compose up -d admin-panel
```

### Фрагмент docker-compose.yml

```yaml
admin-panel:
  build: ./services/admin-panel
  container_name: admin-panel
  restart: unless-stopped
  environment:
    - ADMIN_PANEL_BRAND=${ADMIN_PANEL_BRAND:-Corp AI}
    - ADMIN_UI_PASSWORD=${ADMIN_UI_PASSWORD:-}
    - CORP_DIR_URL=http://corp-dir-broker:8652
    - PROVISIONER_URL=http://provisioner:8650
    - BROKER_INTERNAL_AUTH=${BROKER_INTERNAL_AUTH}
    - HERMES_IMAGE=${HERMES_IMAGE:-your-registry/hermes-agent:latest}
  ports: ["127.0.0.1:8655:8655"]
  networks: [hermes]
  depends_on: [corp-dir-broker, provisioner]
```

## Как заменить mock на реальные данные

1. **Метрики активности пользователей** — подключи к registry.db (если
   provisioner ведёт лог запросов) или к audit-сервису. Замени функцию
   `_mock_metrics_for_user()` в main.py на реальный SQL-запрос.

2. **Статус runtime** — добавь `GET /runtimes` в provisioner (возвращает
   список контейнеров со статусом), убери TODO в `_provisioner_runtimes()`.

3. **Системная информация** — замени `_mock_system()` на вызов Docker API
   (docker.sock смонтирован в provisioner — используй его или отдельный
   sidecar-сервис метрик).

4. **Аудит-лог** — создай audit-сервис (append-only store, контракт в
   docs/AUDIT.md) и замени `_mock_audit()` на HTTP-запрос к нему.

5. **Каналы** — подключи лог-агрегатор (Loki, Elasticsearch) или метрики
   OpenWebUI / Telegram-gateway и замени `_mock_channels()`.

6. **Вкладки Files / Tasks / Skills / Settings** — см. IMPLEMENT.md.

## Авторизация

Cookie-сессия. Токены хранятся в памяти процесса (сбрасываются при рестарте).
Для продакшна замени `_sessions: set` на Redis или подписанные JWT.
