# Схемы данных

Платформа хранит немного состояния, но оно важно для маршрутизации, учёта и
эксплуатации. Здесь — обезличенные **референс-схемы**. В шаблоне заглушки держат
данные в памяти/SQLite; в проде это обычно PostgreSQL.

DDL-файлы: [`schema/registry.sql`](../schema/registry.sql),
[`schema/key-broker.sql`](../schema/key-broker.sql).

## 1. Registry (proxy / provisioner)

Учёт пользователей, их runtime и активности. На неё опираются резолв личности,
idle-shutdown, health и отчёты.

| Таблица | Назначение |
|---|---|
| `users` | сотрудник ↔ его runtime: email, runtime_id, контейнер, статус, `last_seen_at`, `archived_at`. |
| `sessions` | сессии работы (канал, время старта) — для аналитики. |
| `message_events` | события сообщений (канал, направление, время) — счётчики «за 7 дней». |
| `telegram_mux_seen` | дедуп Telegram: `runtime_id` → `last_seen_update_id` (watermark, чтобы рестарт не дублировал апдейты). |

```mermaid
erDiagram
    users ||--o{ sessions : has
    users ||--o{ message_events : generates
    users ||--o| telegram_mux_seen : tracks
    users {
        text email PK
        text runtime_id
        text container_name
        text status
        timestamp created_at
        timestamp last_seen_at
        timestamp archived_at
    }
    sessions { text session_id PK; text user_email FK; text channel; timestamp started_at }
    message_events { integer id PK; text user_email FK; text channel; text direction; timestamp ts }
    telegram_mux_seen { text runtime_id PK; bigint last_seen_update_id; timestamp updated_at }
```

## 2. Key-broker

Хранилище per-user ключей к LLM-шлюзу. Ключи — **зашифрованы at-rest**
(в шаблоне заглушка генерит детерминированно; в проде — pgcrypto/Vault).

| Таблица | Назначение |
|---|---|
| `keys` | `user_id` → зашифрованный виртуальный ключ, alias, `created_at`, `rotated_at`. |

## 3. Память (внешний провайдер)

Память — не таблица платформы, а внешний сервис (см. [memory/README](../memory/README.md)).
Полезно вести **реестр банков**: `user:<runtime_id>` (личные, rw),
`project:<slug>`, `corp:<org>` (read-only). Это организационная таблица, не часть
рантайма; шаблон-DDL — в `schema/registry.sql` (таблица `memory_banks`, опционально).

## Применение

```bash
# SQLite (заглушки/пилот)
sqlite3 registry.db   < schema/registry.sql
sqlite3 keybroker.db  < schema/key-broker.sql
# PostgreSQL (прод) — синтаксис совместим; при желании заменить TEXT PK на uuid.
```

Схемы — образец: подгоняйте типы и индексы под свою СУБД и нагрузку.
