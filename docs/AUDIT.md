# Аудит

Все межагентные и привилегированные операции логируются. Аудит-лог —
цепочка доверия: изменять или удалять записи нельзя, можно только редактировать
(mark_redacted) с сохранением факта редактирования.

---

## 1. Схема записи

Минимальный набор полей каждой audit-записи:

```json
{
  "audit_id":       "aud_01j...",
  "ts":             "2026-06-16T09:04:12.345Z",
  "event_type":     "a2a.status_check",
  "actor":          {"type": "agent", "id": "acct-bot", "runtime": "hermes-u-acct-bot"},
  "subject":        {"type": "user",  "id": "user@example.com", "runtime": "hermes-u-user"},
  "action":         "status_check",
  "outcome":        "allowed",
  "tags":           ["a2a_session", "public_scope"],
  "legal_basis":    null,
  "redacted":       false,
  "redact_reason":  null,
  "redacted_at":    null,
  "session_id":     "sess_abc123",
  "request_id":     "req_xyz456",
  "payload_ref":    "s3://audit-bucket/payloads/req_xyz456.zst"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `audit_id` | string | Уникальный идентификатор записи (ULID) |
| `ts` | ISO 8601 UTC | Время события |
| `event_type` | string | Тип события (см. §2) |
| `actor` | object | Кто инициировал: агент, пользователь, система |
| `subject` | object | На кого направлено действие |
| `action` | string | Конкретное действие / tool-call |
| `outcome` | enum | `allowed` / `denied` / `cancelled` / `pending` |
| `tags` | string[] | Метки: `a2a_session`, `privileged`, `pii`, `cron`, ... |
| `legal_basis` | string\|null | Основание обработки ПД (см. §5) |
| `redacted` | bool | Была ли запись отредактирована |
| `redact_reason` | string\|null | Причина редактирования |
| `redacted_at` | ISO 8601\|null | Когда отредактировано |
| `session_id` | string | ID сессии агента |
| `request_id` | string | ID запроса (для трассировки) |
| `payload_ref` | string\|null | Ссылка на хранилище полного payload (опционально) |

---

## 2. Что логируется (scope)

### Обязательно

| Категория | Примеры событий |
|---|---|
| **Межагентные операции (A2A)** | consent-запрос, consent granted/denied, approval pending/approved/cancelled, delegation, tool-call в рамках a2a_session |
| **Привилегированные операции** | эскалация approval, auto_cancel_on_role_change, OOO-делегирование, redact записи |
| **Управление доступом** | block/unblock агента, смена роли пользователя, ротация кредов |
| **Операции с ПД** | любое действие с тегом `pii`, retain/recall корп-банка, broker-вызов с персональными данными |
| **Security-события** | срабатывание детектора инъекций в proxy, отклонённые запросы по политике |
| **Cron-доставки** | каждая cron_delivery с job_id, mode, message_id, outcome |

### По усмотрению (но рекомендуется)

- Все tool-call агента в privileged-сессиях.
- Broker-запросы с результатом (без payload, только факт и outcome).
- Изменения конфигурации runtime (provisioner).

### Не логируется

- Содержимое обычных пользовательских сообщений (не A2A, не privileged).
- LLM-ответы (только факт вызова, без текста).
- Личная память пользователя (retain/recall личного банка).

---

## 3. Redact-not-delete

Audit-лог — цепочка доверия. **Hard-delete записей запрещён.**

Если запись содержит данные, которые нужно скрыть (например, ошибочно
попавшие ПД), применяется `mark_redacted`:

```json
{
  "audit_id": "aud_01j...",
  "redacted": true,
  "redact_reason": "pii_leaked_by_error",
  "redacted_at": "2026-06-16T10:00:00Z",
  "redacted_by": "admin@example.com"
}
```

- Метаданные записи (ts, event_type, actor, subject, outcome) сохраняются.
- Чувствительный payload (поле `payload_ref`) удаляется из хранилища отдельно
  (storage-side delete), но факт его существования и удаления остаётся в записи.
- Кто и когда выполнил redact — само является аудит-событием (`audit.redact`).

---

## 4. Retention (сроки хранения)

| Категория записей | Срок хранения | Основание |
|---|---|---|
| A2A и privileged операции | 5 лет | корпоративная политика |
| Операции с ПД (тег `pii`) | согласно legal_basis + 1 год | 152-ФЗ |
| Security-события | 3 года | корпоративная политика |
| Cron-доставки | 1 год | операционная необходимость |
| Редактирования (redact) | бессрочно | chain-of-custody |

После истечения срока записи архивируются (cold storage), не удаляются. Физическое
удаление — только по решению ответственного за обработку ПД и только для записей
с ПД по истечении retention + 1 год.

---

## 5. Legal basis — основание обработки ПД (152-ФЗ)

При любой операции, затрагивающей персональные данные, поле `legal_basis`
заполняется обязательно. Варианты:

| Значение | Описание |
|---|---|
| `consent` | Субъект дал согласие на обработку (ст. 6 ч. 1 п. 1) |
| `contract` | Обработка необходима для исполнения договора (ст. 6 ч. 1 п. 5) |
| `legitimate_interest` | Законный интерес оператора (ст. 6 ч. 1 п. 7) |
| `legal_obligation` | Обработка требуется законом (ст. 6 ч. 1 п. 2) |
| `vital_interest` | Жизненно важные интересы субъекта (ст. 6 ч. 1 п. 6) |

Если legal_basis не определён — операция с ПД не выполняется (fail-closed).

Ответственный за ведение реестра оснований обработки — отдельная роль (DPO или
аналог). Реестр хранится вне audit-лога, ссылка на запись реестра — в поле
`legal_basis_ref` (опционально расширяет схему).

---

## 6. Где хранить

### Требования к хранилищу

- **Append-only**: запись добавляется, существующая не изменяется на уровне хранилища.
- **Шифрование at-rest**: ключ отдельно от данных.
- **Изолированный доступ**: audit-хранилище не доступно из user-runtime; только
  из отдельного audit-сервиса с явно ограниченными правами.
- **Retention enforcement**: хранилище само умеет переводить записи в cold storage
  по TTL; не полагается на ручные операции.

### Варианты (образцы, не endorsement)

| Вариант | Подходит для |
|---|---|
| PostgreSQL + append-only table (INSERT only, без UPDATE/DELETE прав у сервиса) | малый / средний масштаб, self-hosted |
| ClickHouse (append-only движок) | большой объём событий, быстрые аналитические запросы |
| Object storage (S3-совместимый) с Object Lock | простое решение, compliance-ready |
| Loki (log aggregation) | если уже используется в стеке |

### Сетевая изоляция

Audit-сервис слушает только внутреннюю docker-сеть. Наружу audit-данные не уходят.
Доступ к cold storage — через внутренний сервис-посредник, не напрямую из агентов.

```
user-runtime   →   [запрещено]   →   audit store
identity-proxy →   audit-service  →   audit store
a2a-handler    →   audit-service  →   audit store
```
