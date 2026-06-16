-- Registry (proxy/provisioner) — учёт пользователей, runtime и активности.
-- Образец. SQLite-совместимо; для PostgreSQL замените при желании TEXT PK на uuid,
-- а INTEGER PRIMARY KEY AUTOINCREMENT на BIGSERIAL.

CREATE TABLE IF NOT EXISTS users (
    email           TEXT PRIMARY KEY,          -- корпоративный email = идентификатор
    runtime_id      TEXT UNIQUE,               -- стабильный id рантайма (для имён банков/токенов)
    container_name  TEXT,                      -- hermes-u-<slug>
    status          TEXT DEFAULT 'active',     -- active | idle | archived
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP,                 -- для idle-shutdown
    archived_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    user_email   TEXT REFERENCES users(email),
    channel      TEXT,                          -- webui | telegram
    started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_email);

CREATE TABLE IF NOT EXISTS message_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email   TEXT REFERENCES users(email),
    channel      TEXT,                          -- webui | telegram
    direction    TEXT,                          -- in | out
    ts           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_msg_user_ts ON message_events(user_email, ts);

-- Дедуп Telegram-апдейтов на уровне MUX (watermark, чтобы рестарт не дублировал).
CREATE TABLE IF NOT EXISTS telegram_mux_seen (
    runtime_id            TEXT PRIMARY KEY,
    last_seen_update_id   BIGINT,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Опционально: реестр банков памяти (организационный учёт).
CREATE TABLE IF NOT EXISTS memory_banks (
    bank_id     TEXT PRIMARY KEY,               -- user:<runtime_id> | project:<slug> | corp:<org>
    kind        TEXT,                           -- user | project | corp
    read_only   INTEGER DEFAULT 0,              -- 1 для corp:*
    owner       TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
