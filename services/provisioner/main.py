"""provisioner — по контейнеру-агенту на каждого пользователя.

Owns узкий набор Docker-операций: создать/запустить/остановить персональный
runtime. Ключевой защитный момент — strip_platform_env(): при создании
user-runtime из окружения ВЫРЕЗАЮТСЯ секреты платформы (токены ботов, ключи
провайдеров), чтобы пользовательский агент физически не мог их прочитать.

Дополнительно:
  - _fake_telegram_token()    — per-user токен для Telegram MUX-прокси.
  - _ensure_user_config_yaml() — инжектирует config.yaml в каталог пользователя.
  - _provision_auth()         — управляет способом передачи auth (none/copy/mount).

Это скелет: логика именования, идемпотентность и срезание секретов
реализованы; том/конфиг под вашу сборку Hermes-Agent помечены TODO.
"""
import hmac
import hashlib
import json
import os
import re
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

try:
    import yaml  # опционально — PyYAML не в базовых deps заглушки
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

try:
    import docker  # доступен в контейнере с примонтированным docker.sock
    _client = docker.from_env()
except Exception:
    _client = None  # скелет можно импортировать и без Docker

app = FastAPI(title="provisioner")

INTERNAL_AUTH = os.getenv("BROKER_INTERNAL_AUTH", "")
HERMES_IMAGE = os.getenv("HERMES_IMAGE", "nousresearch/hermes-agent:latest")
NETWORK = os.getenv("HERMES_DOCKER_NETWORK", "hermes_hermes")
PREFIX = os.getenv("CONTAINER_PREFIX", "hermes-u-")
PORT = os.getenv("HERMES_INTERNAL_API_PORT", "8642")

STRIP_PREFIXES = tuple(p for p in os.getenv("USER_RUNTIME_STRIP_ENV_PREFIXES", "TELEGRAM_,DISCORD_,SLACK_").split(",") if p)
STRIP_KEYS = {k for k in os.getenv("USER_RUNTIME_STRIP_ENV_KEYS", "LLM_API_KEY,FALLBACK_API_KEY").split(",") if k}

# --- key-broker ---
KEYBROKER_URL = os.getenv("KEYBROKER_URL", "http://key-broker:8700")
KEYBROKER_SYSTEM_SECRET = os.getenv("KEYBROKER_SYSTEM_SECRET", "")

# --- Telegram MUX ---
TELEGRAM_MUX_SECRET = os.getenv("TELEGRAM_MUX_SECRET", "")
TELEGRAM_MUX_BOT_ID = os.getenv("TELEGRAM_MUX_BOT_ID", "0")  # числовой bot_id, плейсхолдер

# --- Конфигурация runtime ---
# copy — файл копируется в каталог пользователя до старта контейнера;
#   контейнер получает том с копией. Безопаснее: изменение оригинала не
#   влияет на запущенный runtime, а у каждого пользователя своя копия.
# mount — RO-маунт оригинала. Удобнее в dev, но требует, чтобы исходный
#   файл существовал на хосте; при ошибке монтирования контейнер не стартует.
USER_RUNTIME_CONFIG_MODE = os.getenv("USER_RUNTIME_CONFIG_MODE", "copy")  # copy | mount

# none  — auth не передаётся: ключи только из key-broker (РЕКОМЕНДУЕТСЯ).
# copy  — auth.json копируется в каталог пользователя (контейнер читает копию).
# mount — RO-маунт auth.json внутрь контейнера. КОМПРОМИСС: пользователь внутри
#         контейнера всё равно может прочитать файл через cat/printenv.
#         Используйте только если у вас нет key-broker-а.
USER_RUNTIME_AUTH_MODE = os.getenv("USER_RUNTIME_AUTH_MODE", "none")  # 