#!/usr/bin/env bash
# Генератор виртуального ключа LiteLLM на сервис/пользователя.
# Без секретов: master-key и адрес берутся из окружения.
#   LITELLM_BASE_URL=http://localhost:4000 LITELLM_MASTER_KEY=... ./gen_key.sh "team-hermes"
set -euo pipefail
: "${LITELLM_BASE_URL:?set LITELLM_BASE_URL}"
: "${LITELLM_MASTER_KEY:?set LITELLM_MASTER_KEY}"
ALIAS="${1:-default}"
curl -s -X POST "$LITELLM_BASE_URL/key/generate" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"key_alias\":\"$ALIAS\",\"models\":[\"hermes-agent\"]}" | python3 -m json.tool
