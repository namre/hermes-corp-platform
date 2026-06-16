-- Key-broker — per-user ключи к LLM-шлюзу. Образец.
-- ВАЖНО: encrypted_key хранится ТОЛЬКО в зашифрованном виде (pgcrypto/Vault/KMS).
-- В шаблоне-заглушке значение генерится детерминированно и не является секретом.

CREATE TABLE IF NOT EXISTS keys (
    user_id        TEXT PRIMARY KEY,            -- email или runtime_id
    encrypted_key  BLOB NOT NULL,               -- шифр виртуального ключа (НЕ открытый текст)
    key_alias      TEXT,                        -- человекочитаемое имя ключа в LLM-шлюзе
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rotated_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_keys_alias ON keys(key_alias);
