# Охват шаблона и дорожная карта

Что этот шаблон уже показывает, что намеренно оставлено заглушкой и **чего пока
нет**. Честная карта границ — чтобы не выдавать незакрытое за готовое.

## Уже покрыто

- Мультитенантность: `identity-proxy` (резолв личности, security-детектор) +
  `provisioner` (контейнер на пользователя, `strip_platform_env`).
- Брокеры с контрактом: каталог сотрудников, файлы, задачи (заглушка + образец).
- Единый LLM-шлюз (LiteLLM-образец), генератор виртуальных ключей.
- Память: контракт двух банков (личный + корп read-only), naming policy.
- Интерфейс: OpenWebUI (проброс личности) + файловый слой (фильтр + эндпоинты).
- Принципы, безопасность (базово), метод «заглушка + образец + инструкция для LLM».

**Добавлено в раунде закрытия пробелов:**

- `key-broker` (per-user ключи) + углублённый `provisioner` (инъекция `config.yaml`,
  режимы auth none/copy/mount, fake-токен Telegram) + `tools/check-config-schema.sh`.
- `telegram-gateway` (MUX-заглушка) + [TELEGRAM_MUX](TELEGRAM_MUX.md) + [ONBOARDING](ONBOARDING.md).
- Операционный слой: `scripts/` (бэкап, idle-shutdown, doctor, admin-cli, usage) +
  [OPERATIONS](OPERATIONS.md) + [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md) + CHANGELOG/BUGS-шаблоны.
- Контракты: [A2A](A2A.md), [AUDIT](AUDIT.md), [NETWORK](NETWORK.md),
  [TOOL_POLICY](TOOL_POLICY.md), [INGESTION](../memory/INGESTION.md), `company/skills/` (пример SKILL.md).

Таблицы ниже — исходный бэклог аудита; большинство пунктов Tier 1–2 теперь закрыто
документом/заглушкой. Остаётся как карта для углубления (реальные интеграции вместо
образцов, голос, мультиплатформа, cron-modes).

## Пробелы (по итогам аудита боевой системы)

Severity: **H** критично для прод-развёртывания · **M** важно · **L** желательно.
Тип: 🔧 добавить рабочий код/заглушку · 📄 добавить документ/контракт.

### Группа 1. Telegram-канал и мультиплатформенность — H

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 1.1 | **Telegram MUX**: один бот → много пользователей (fake per-user токен через HMAC, очереди, passthrough Bot API) | H | 📄+🔧 |
| 1.2 | Webhook-аутентификация: секрет в пути, проверка владения chat_id, fail-closed для неизвестного tg_id | H | 📄 |
| 1.3 | Онбординг: первый контакт → welcome → таймзона → OAuth-привязка корп-аккаунта | H | 📄 |
| 1.4 | Реестр платформ (plugin-адаптеры): как добавить Teams/IRC без правки ядра | M | 📄 |
| 1.5 | Голос: входящий voice → транскрипт (STT), исходящий → TTS (опц.) | M | 📄 |
| 1.6 | UX генерации: typing-индикатор, реакции, дедуп `update_id` при рестарте | L | 📄 |
| 1.7 | Уведомления админам (`/notify/admins`) при security-событиях | L | 📄 |

### Группа 2. Глубина provisioner: конфиг и креды в runtime — H

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 2.1 | Инъекция per-user `config.yaml` (platforms.telegram, mcp_servers, memory.provider, locale/tts) | H | 🔧 |
| 2.2 | Режимы `auth.json`/config: `mount` vs `copy` vs `none` + ротация | H | 🔧+📄 |
| 2.3 | Схема `config.yaml` + smoke-проверка (`check-config-schema.sh`) | M | 🔧 |
| 2.4 | Разграничение admin-runtime vs user-runtime (что монтируется/наследуется) | M | 📄 |

### Группа 3. Изоляция кредов: key-broker — H

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 3.1 | **key-broker** как сервис-заглушка: per-user LLM-ключи, Bearer system-secret, postgres/sqlite | H | 🔧 |
| 3.2 | Честный разбор остаточного риска RO-mount `auth.json` (SECRET_ISOLATION) | M | 📄 |
| 3.3 | Per-user LLM-ключи и model-forcing вместо общего ключа | M | 📄 |

### Группа 4. Корпоративные skills — H/M

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 4.1 | `company/skills/`: формат `SKILL.md`, пример корп-контекста, монтирование RO в runtime | H | 🔧+📄 |
| 4.2 | Политика инструментов обычного пользователя (enforcement границами контейнера, не toggle) | M | 📄 |

### Группа 5. Операционный слой — H (отсутствует целиком)

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 5.1 | Бэкап per-user runtime (whitelist, retention) | H | 🔧+📄 |
| 5.2 | Idle-shutdown простаивающих контейнеров | H | 🔧 |
| 5.3 | Runbook обновления/отката базового агента (pin по digest, smoke, rollback) | H | 📄 |
| 5.4 | Health/диагностика (`doctor`-скрипт, 10+ проверок) | H | 🔧 |
| 5.5 | Admin-CLI: list/restart/bulk-config | M | 🔧 |
| 5.6 | Практика CHANGELOG + BUGS, схема registry.db (учёт пользователей) | M | 📄 |
| 5.7 | Очистка старых данных, weekly-usage, code-drift guard | L | 🔧 |

### Группа 6. A2A — межагентное взаимодействие — H (но частью ещё не построено)

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 6.1 | **A2A governance**: consent-рукопожатие, approval по политике (эскалация, fail-closed), public scope (hardcoded enum), delegation при OOO | H | 📄 |
| 6.2 | Scoped toolset при A2A — известное ограничение и workaround-слойка | M | 📄 |
| 6.3 | Cron delivery modes (append/replace/edit) + session write-back | M | 📄 |

> A2A в боевой системе сам частью в разработке — для шаблона это **дизайн-контракт
> и роадмап**, не рабочий код. Подаём честно как замысел.

### Группа 7. Память: глубина — M/H

| # | Пробел | Severity | Тип |
|---|---|---|---|
| 7.1 | Ingestion-конвейер корп-памяти: источник → факты → метаданные → cron, двойной read-only | H | 📄 |
| 7.2 | Приватный транспорт до провайдера памяти (m