#!/usr/bin/env bash
# idle-shutdown.sh
# Поиск и остановка простаивающих per-user runtime контейнеров.
# Сохраняет данные (остановка контейнера, а не удаление).
# provisioner поднимет контейнер снова при следующем запросе пользователя.
#
# Использование:
#   DRY_RUN=true bash scripts/idle-shutdown.sh                 # просмотр без изменений
#   IDLE_DAYS=3 bash scripts/idle-shutdown.sh                  # останавливает неактивных >3 дня
#
# Переменные окружения:
#   IDLE_DAYS  - дней неактивности перед остановкой (по умолчанию 7)
#   DRY_RUN    - если true, показывает действия без выполнения
#
# Источник last_seen:
#   - docker inspect <container> | grep CreatedAt / State.StartedAt
#   - либо файл .last_seen в user-runtime (если provisioner его создаёт)

set -euo pipefail

readonly IDLE_DAYS="${IDLE_DAYS:-7}"
readonly DRY_RUN="${DRY_RUN:-false}"
readonly IDLE_THRESHOLD=$((IDLE_DAYS * 86400))  # в секундах

log() {
    local level="$1"
    shift
    local msg="$@"
    echo "[${level}] $(date '+%Y-%m-%d %H:%M:%S') ${msg}"
}

run_cmd() {
    local cmd="$@"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY_RUN" "${cmd}"
    else
        eval "${cmd}"
    fi
}

get_container_last_activity() {
    local container_id="$1"
    # Получаем время последнего logDriver event (примерно - время последней активности)
    # TODO(REPLACE): Заменить на реальный источник last_seen (может быть API provisioner или .last_seen файл)
    docker inspect "${container_id}" --format='{{.State.StartedAt}}' 2>/dev/null || echo ""
}

convert_timestamp_to_epoch() {
    local ts="$1"
    # ts формат: 2024-12-15T10:30:45.123Z
    date -d "${ts}" +%s 2>/dev/null || echo 0
}

main() {
    log "INFO" "Поиск простаивающих контейнеров (>${IDLE_DAYS} дней)"
    log "INFO" "DRY_RUN=${DRY_RUN}"

    local current_epoch=$(date +%s)
    local stopped_count=0
    local checked_count=0

    # Поиск контейнеров с именем hermes-u-* (per-user runtime)
    while IFS= read -r container_id; do
        ((checked_count++))
        local container_name=$(docker inspect "${container_id}" --format='{{.Name}}' | sed 's/^\//')

        # TODO(REPLACE): Получить реальное время последней активности
        # В боевой системе это может быть логирование в provisioner API,
        # или time последнего успешного запроса, или .last_seen метаfile
        local started_at=$(get_container_last_activity "${container_id}")

        if [[ -z "${started_at}" ]]; then
            log "WARN" "${container_name}: не удалось определить время активности"
            continue
        fi

        local start_epoch=$(convert_timestamp_to_epoch "${started_at}")
        local age=$((current_epoch - start_epoch))

        if [[ ${age} -gt ${IDLE_THRESHOLD} ]]; then
            local age_days=$((age / 86400))
            log "INFO" "${container_name}: ${age_days} дней неактивности → остановка"
            run_cmd "docker stop '${container_id}' 2>/dev/null"
            ((stopped_count++))
        else
            local age_days=$((age / 86400))
            log "DEBUG" "${container_name}: ${age_days} дней (активен)"
        fi
    done < <(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null || true)

    log "INFO" "Проверено: ${checked_count}, остановлено: ${stopped_count}"
    log "INFO" "Контейнеры могут быть перезапущены provisioner'ом при следующем запросе"
}

main "$@"
