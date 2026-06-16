#!/usr/bin/env bash
# admin-cli.sh
# Диспетчер команд администратора для управления платформой.
# Поддерживает: list пользователей, restart-user, restart-all, user-config.
#
# Использование:
#   bash scripts/admin-cli.sh list                           # список пользователей
#   bash scripts/admin-cli.sh list --idle                    # список с idle-статусом
#   bash scripts/admin-cli.sh restart-user alice@example.com # рестарт пользователя
#   bash scripts/admin-cli.sh restart-all                    # рестарт всех runtime
#   bash scripts/admin-cli.sh user-config alice@example.com  # конфиг пользователя
#
# Переменные окружения:
#   PROVISIONER_URL - URL provisioner API (по умолчанию http://127.0.0.1:8650)
#   IDLE_DAYS       - дней для определения idle-статуса (по умолчанию 3)

set -euo pipefail

readonly PROVISIONER_URL="${PROVISIONER_URL:-http://127.0.0.1:8650}"
readonly IDLE_DAYS="${IDLE_DAYS:-3}"
readonly IDLE_THRESHOLD=$((IDLE_DAYS * 86400))

log() {
    local level="$1"
    shift
    echo "[${level}] $@"
}

cmd_list() {
    local show_idle=false
    if [[ "${1:-}" == "--idle" ]]; then
        show_idle=true
    fi

    log "INFO" "Список пользователей:"
    echo ""
    printf "%-30s %-10s %-20s %-30s\n" "Email" "Status" "Last Activity" "Container"
    echo "$(printf '%.0s-' {1..90})"

    local current_epoch=$(date +%s)

    # TODO(REPLACE): Получить список пользователей из реального источника:
    # - docker ps с фильтром hermes-u-*
    # - provisioner API /users
    # - corp-dir-broker /users
    while IFS= read -r container_id; do
        local container_name=$(docker inspect "${container_id}" --format='{{.Name}}' | sed 's/^\//')

        # Извлекаем email из имени контейнера (hermes-u-<slug> → email)
        local email_slug=$(echo "${container_name}" | sed 's/^hermes-u-//')
        # TODO(REPLACE): Заменить на реальный de-slug алгоритм
        local email="${email_slug}@example.com"

        # Получаем время последней активности
        local started_at=$(docker inspect "${container_id}" --format='{{.State.StartedAt}}' 2>/dev/null || echo "")
        local status=$(docker inspect "${container_id}" --format='{{.State.Status}}' 2>/dev/null || echo "unknown")

        local age_days=0
        if [[ -n "${started_at}" ]]; then
            local start_epoch=$(date -d "${started_at}" +%s 2>/dev/null || echo 0)
            local age=$((current_epoch - start_epoch))
            age_days=$((age / 86400))
        fi

        # Определяем idle-статус
        local idle_status="active"
        if [[ ${age_days} -gt ${IDLE_DAYS} ]]; then
            idle_status="idle"
        fi

        if [[ "${show_idle}" == "false" || "${idle_status}" == "idle" ]]; then
            printf "%-30s %-10s %-20s %-30s\n" "${email}" "${idle_status}" "${age_days}d" "${container_name}"
        fi
    done < <(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null || true)

    echo ""
}

cmd_restart_user() {
    local email="$1"

    if [[ -z "${email}" ]]; then
        log "ERROR" "Требуется email: restart-user <email>"
        return 1
    fi

    # TODO(REPLACE): Заменить на реальный slug алгоритм (обратный к de-slug выше)
    local slug=$(echo "${email}" | sed 's/@.*//' | tr '[:upper:]' '[:lower:]')
    local container_name="hermes-u-${slug}"

    log "INFO" "Рестарт контейнера ${container_name}..."

    # Проверяем, существует ли контейнер
    if ! docker ps -a --filter "name=${container_name}" --quiet 2>/dev/null | grep -q .; then
        log "WARN" "Контейнер ${container_name} не найден"
        return 1
    fi

    # Остаём контейнер
    docker stop "${container_name}" 2>/dev/null || true
    log "OK" "Контейнер остановлен"

    # TODO(REPLACE): Позвать provisioner API для перезапуска
    # curl -X POST "${PROVISIONER_URL}/users/${email}/restart" \
    #   -H "Authorization: Bearer ${PROVISIONER_TOKEN}" \
    #   -H "Content-Type: application/json"

    log "INFO" "Provisioner воссоздаст контейнер при следующем запросе"
}

cmd_restart_all() {
    log "INFO" "Рестарт всех per-user runtime контейнеров..."

    local restarted=0
    while IFS= read -r container_id; do
        local container_name=$(docker inspect "${container_id}" --format='{{.Name}}' | sed 's/^\//')
        docker stop "${container_id}" 2>/dev/null || true
        ((restarted++))
    done < <(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null || true)

    log "OK" "Остановлено ${restarted} контейнеров"
    log "INFO" "Provisioner воссоздаст их при следующих запросах"
}

cmd_user_config() {
    local email="$1"

    if [[ -z "${email}" ]]; then
        log "ERROR" "Требуется email: user-config <email>"
        return 1
    fi

    # TODO(REPLACE): Получить конфиг пользователя из реального источника:
    # - docker inspect <container>
    # - provisioner API /users/<email>/config
    # - user-runtime .env / config.yaml

    log "INFO" "Конфиг пользователя ${email}:"
    echo ""

    local slug=$(echo "${email}" | sed 's/@.*//' | tr '[:upper:]' '[:lower:]')
    local container_name="hermes-u-${slug}"

    if docker ps -a --filter "name=${container_name}" --quiet 2>/dev/null | grep -q .; then
        log "OK" "Container: ${container_name}"

        # Показываем environment variables (без секретов)
        echo "Environment variables (filtered):"
        docker inspect "${container_name}" --format='{{json .Config.Env}}' 2>/dev/null | \
            grep -o '"[^"]*"' | \
            grep -v -E '"(LLM_|TELEGRAM_|OPENAI_|API_KEY)' | \
            head -20
    else
        log "WARN" "Контейнер ${container_name} не найден или остановлен"
    fi
    echo ""
}

cmd_help() {
    cat <<EOF
Hermes Admin CLI — управление платформой

Команды:
  list                              Список всех пользователей
  list --idle                       Только неактивные пользователи
  restart-user <email>              Рестарт user-runtime
  restart-all                       Рестарт всех user-runtime
  user-config <email>               Показать конфиг пользователя
  help                              Эта справка

Примеры:
  bash scripts/admin-cli.sh list
  bash scripts/admin-cli.sh restart-user alice@example.com
  bash scripts/admin-cli.sh restart-all

Переменные:
  PROVISIONER_URL                   URL provisioner API (default: http://127.0.0.1:8650)
  IDLE_DAYS                         Дней для idle-статуса (default: 3)
EOF
}

main() {
    local cmd="${1:-help}"
    shift || true

    case "${cmd}" in
        list)
            cmd_list "$@"
            ;;
        restart-user)
            cmd_restart_user "$@"
            ;;
        restart-all)
            cmd_restart_all "$@"
            ;;
        user-config)
            cmd_user_config "$@"
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            log "ERROR" "Неизвестная команда: ${cmd}"
            cmd_help
            return 1
            ;;
    esac
}

main "$@"
