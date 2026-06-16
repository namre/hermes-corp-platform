#!/usr/bin/env bash
# check-config-schema.sh — smoke-проверка per-user config.yaml
#
# Итерирует users/*/config.yaml и проверяет наличие ключевых полей.
# Завершается с exit 0, если все файлы прошли; exit 1 при первой ошибке.
#
# Использование:
#   bash tools/check-config-schema.sh [USERS_DIR]
#
# Аргументы:
#   USERS_DIR — каталог с per-user папками (дефолт: ./users)
#
# Зависимости: bash, grep (нет python/yq — намеренно, минимум зависимостей).

set -euo pipefail

USERS_DIR="${1:-./users}"
REQUIRED_FIELDS=(
    "platforms.telegram"
    "mcp_servers"
    "memory.provider"
    "display.language"
)

if [[ ! -d "$USERS_DIR" ]]; then
    echo "INFO: users dir not found: $USERS_DIR — nothing to check."
    exit 0
fi

FILES=()
while IFS= read -r -d '' f; do
    FILES+=("$f")
done < <(find "$USERS_DIR" -name "config.yaml" -print0 2>/dev/null)

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "INFO: no config.yaml files found under $USERS_DIR — nothing to check."
    exit 0
fi

ERRORS=0

for cfg in "${FILES[@]}"; do
    echo "--- checking: $cfg"
    for field in "${REQUIRED_FIELDS[@]}"; do
        # Ищем поле как ключ YAML: «field_name:» в любом месте файла.
        # Простая эвристика через grep достаточна для smoke-check.
        key="${field##*.}"   # берём последний сегмент (после последней точки)
        if ! grep -qE "^\s*${key}\s*:" "$cfg" 2>/dev/null; then
            echo "  FAIL: missing field '${field}' (key '${key}') in $cfg"
            ERRORS=$((ERRORS + 1))
        else
            echo "  OK:   ${field}"
        fi
    done
done

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "RESULT: FAIL — $ERRORS missing field(s) across ${#FILES[@]} file(s)."
    exit 1
else
    echo "RESULT: OK — all ${#FILES[@]} config(s) passed."
    exit 0
fi
