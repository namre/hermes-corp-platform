# IMPLEMENT — key-broker (паста для LLM-ассистента)

Скопируйте в чат с LLM-ассистентом, заполнив <…>.

---

Ты реализуешь **key-broker** для корпоративной агентской платформы. Сейчас это
заглушка (`main.py`) на HMAC + in-memory кэш. Замени на продакшн-реализацию,
СОХРАНИВ контракт.

## Моя система

- LLM-шлюз: <LiteLLM на http://llm-gateway:4000 | другой OpenAI-совместимый>
- БД для хранения ключей: <PostgreSQL | только in-memory | HashiCorp Vault>
- Нужна ротация ключей: <да, раз в N дней | нет>
- Нужны per-user лимиты (rpm/tpm): <да | нет>

## Контракт (не менять)

```
POST /v1/keys
  Authorization: Bearer <KEYBROKER_SYSTEM_SECRET>
  {"user_id": "alice@example.com"}
  → {"key": "vk-...", "user_id": "...", "source": "cache|generated"}

GET /health → {"status": "ok", ...}
```

401 при несовпадении Bearer. 400 при пустом user_id.

## Обязательные инварианты

1. Ключи зашифрованы at-rest — никогда не хранить plain-text в БД.
   Используй `pgcrypto.pgp_sym_encrypt(key, $enc_key)` или аналог.
2. Доступ только через `KEYBROKER_SYSTEM_SECRET` — user-runtime этого секрета
   не знает и никогда не должен знать.
3. Никаких хардкоженых секретов — только `os.getenv(...)`.
4. Ротация (если нужна): при вызове `/v1/keys` с `{"rotate": true}` — пересоздать
   ключ, пометить старый как `revoked_at`, передать новый в runtime через provisioner.

## Что реализовать (PostgreSQL + LiteLLM-вариант)

1. **Схема БД**: таблица `user_keys(id, user_id UNIQUE, encrypted_key, created_at,
   expires_at, rotated_at)`. Мастер-ключ шифрования — `KEYBROKER_ENCRYPTION_KEY` из env.

2. **Логика выдачи**:
   - Если запись есть и не истекла — расшифровать и вернуть.
   - Если нет или истекла — запросить у LiteLLM новый virtual key:
     `POST http://llm-gateway:4000/key/generate` с `{"user_id": ..., "rpm_limit": ...,
     "tpm_limit": ...}`. Сохранить зашифрованным.

3. **Ротация**: `POST /v1/keys` с `{"user_id": ..., "rotate": true}` — вызвать
   `/key/regenerate` у LiteLLM, обновить запись.

4. **Аудит**: логировать все выдачи и ротации (user_id, timestamp, source) — без
   значения ключа в логе.

## Переменные окружения

| Переменная | Значение |
|---|---|
| `KEYBROKER_SYSTEM_SECRET` | Bearer-токен доступа к /v1/keys |
| `KEYBROKER_ENCRYPTION_KEY` | Мастер-ключ шифрования at-rest (AES-256 / pgcrypto) |
| `KEYBROKER_DB_URL` | postgresql://... (если PostgreSQL) |
| `LITELLM_ADMIN_URL` | http://llm-gateway:4000 (если LiteLLM) |
| `LITELLM_MASTER_KEY` | Мастер-ключ LiteLLM для /key/generate |
| `KEY_TTL_DAYS` | Срок жизни ключа (дефолт 90) |

Сначала план и DDL-схему, потом код. Сохрани FastAPI + uvicorn, порт 8700.
