# key-broker

Сервис изоляции per-user LLM-ключей. Порт **8700**.

## Зачем

Платформенный мастер-ключ к LLM-шлюзу (LiteLLM или аналог) **не должен попадать
в user-runtime** — иначе любой пользователь может его прочитать через `printenv`
или слив через промпт. key-broker выдаёт каждому пользователю собственный
virtual key с независимыми лимитами. Provisioner запрашивает его перед созданием
контейнера и инжектирует только этот ключ — мастер остаётся скрытым.

## Контракт

```
GET  /health
  → {"status": "ok", "backend": "...", "cached_users": N}

POST /v1/keys
  Authorization: Bearer <KEYBROKER_SYSTEM_SECRET>
  {"user_id": "alice@example.com"}
  → {"key": "vk-<hex>", "user_id": "alice@example.com", "source": "cache|generated"}
```

**401** — при несовпадении или отсутствии Bearer-токена.  
**400** — пустой `user_id`.

Запрос делает только provisioner (и другие доверенные компоненты платформы).
Пользовательский runtime не имеет доступа к key-broker.

## Заглушка (текущая реализация)

Ключ генерируется детерминированно: `HMAC-SHA256(user_id, KEYBROKER_SYSTEM_SECRET)`,
кэшируется в памяти процесса. Перезапуск сервиса инвалидирует кэш, но ключи
воссоздаются с теми же значениями (детерминированность).

**Ограничения заглушки:** нет персистентности, нет ротации, нет per-user лимитов,
нет аудита выдачи.

## Чем заменить (продакшн)

1. **PostgreSQL + pgcrypto** — хранить ключи зашифрованными at-rest мастер-ключом
   из env (`KEYBROKER_ENCRYPTION_KEY`). Таблица `user_keys(user_id, encrypted_key,
   created_at, expires_at, rotated_at)`. Ключ расшифровывается только в памяти
   при выдаче, в БД лежит `pgp_sym_encrypt(key, $master)`.

2. **LiteLLM /key/generate** — если LLM-шлюз это LiteLLM, он умеет выдавать
   virtual keys через свой admin API. key-broker становится тонкой обёрткой:
   `POST http://llm-gateway:4000/key/generate` с лимитами, возвращает LiteLLM
   virtual key. Ротация через `/key/regenerate`.

3. **HashiCorp Vault** — Transit Secrets Engine для шифрования, Dynamic Secrets
   для ротации. Более сложно, но даёт аудит, fine-grained ACL и автоматическую
   ротацию.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `KEYBROKER_SYSTEM_SECRET` | Bearer-токен для запросов к /v1/keys. Обязательный в продакшне. |

## Инварианты (не нарушать при замене)

- Ключи зашифрованы at-rest или хранятся вне диска (только в памяти / Vault).
- Доступ к `/v1/keys` только через `KEYBROKER_SYSTEM_SECRET` — пользовательский
  runtime никогда не должен иметь этого секрета.
- `KEYBROKER_SYSTEM_SECRET` никогда не хардкодится в код или образ.
