#!/usr/bin/env bash
# usage-report.sh
# Анализ активности платформы на основе логов контейнеров.
# Генерирует markdown-отчёт по использованию, ротация логов за 90 дней.
#
# Использование:
#   bash scripts/usage-report.sh                  # генерирует отчёт в stdout
#   bash scripts/usage-report.sh > report.md     # сохранить в файл
#
# Переменные окружения:
#   REPORT_DIR          - директория отчётов (по умолчанию ./reports)
#   REPORT_RETENTION    - дней хранить отчёты (по умолчанию 90)
#   LOG_LOOKBACK_HOURS  - часов истории логов для анализа (по умолчанию 24)

set -euo pipefail

readonly REPORT_DIR="${REPORT_DIR:-.reports}"
readonly REPORT_RETENTION="${REPORT_RETENTION:-90}"
readonly LOG_LOOKBACK_HOURS="${LOG_LOOKBACK_HOURS:-24}"
readonly REPORT_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
readonly REPORT_DATE=$(date +%Y-%m-%d)
readonly REPORT_FILE="${REPORT_DIR}/usage_${REPORT_TIMESTAMP}.md"

log() {
    echo "[INFO] $@" >&2
}

init() {
    mkdir -p "${REPORT_DIR}"
    log "Инициализация отчёта в ${REPORT_DIR}"
}

generate_header() {
    cat <<EOF
# Hermes Corp Platform — Usage Report
**Дата:** ${REPORT_DATE}
**Период:** последние ${LOG_LOOKBACK_HOURS} часов

---

## Краткая статистика

EOF
}

count_active_users() {
    local active=0
    local total=0

    while IFS= read -r container_id; do
        ((total++))
        # TODO(REPLACE): Проверить логи контейнера на активность за последние LOG_LOOKBACK_HOURS
        if docker logs --since "${LOG_LOOKBACK_HOURS}h" "${container_id}" 2>/dev/null | grep -q .; then
            ((active++))
        fi
    done < <(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null || true)

    echo "| Метрика | Значение |"
    echo "|---------|----------|"
    echo "| Всего user-runtime контейнеров | ${total} |"
    echo "| Активных за последние ${LOG_LOOKBACK_HOURS}ч | ${active} |"
    echo "| Простаивающих | $((total - active)) |"
}

generate_user_activity() {
    echo "## Активность пользователей"
    echo ""

    local count=0
    echo "| Пользователь | Контейнер | Статус | Последняя активность |"
    echo "|--------------|-----------|--------|----------------------|"

    while IFS= read -r container_id; do
        local container_name=$(docker inspect "${container_id}" --format='{{.Name}}' | sed 's/^\//')
        local status=$(docker inspect "${container_id}" --format='{{.State.Status}}' | cut -c1-10)

        # TODO(REPLACE): Заменить на реальный de-slug
        local user_slug=$(echo "${container_name}" | sed 's/^hermes-u-//')
        local email="${user_slug}@example.com"

        # Получаем время последнего логирования
        local last_log_time=$(docker logs --since "${LOG_LOOKBACK_HOURS}h" --timestamps "${container_id}" 2>/dev/null | tail -1 | cut -d' ' -f1 || echo "—")

        echo "| ${email} | ${container_name} | ${status} | ${last_log_time} |"
        ((count++))

        if [[ ${count} -ge 50 ]]; then
            echo "| ... | (и ещё $(($(docker ps -a --filter "name=hermes-u-" --quiet | wc -l) - count))) | ... | ... |"
            break
        fi
    done < <(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null || true)

    echo ""
}

generate_service_health() {
    echo "## Здоровье сервисов"
    echo ""

    declare -A services=(
        ["identity-proxy"]="8643"
        ["provisioner"]="8650"
        ["files-broker"]="8651"
        ["corp-dir-broker"]="8652"
        ["tasks-broker"]="8654"
    )

    echo "| Сервис | Порт | Статус |"
    echo "|--------|------|--------|"

    for service in "${!services[@]}"; do
        local port="${services[${service}]}"
        if curl -sf --max-time 3 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
            echo "| ${service} | ${port} | ✓ OK |"
        else
            echo "| ${service} | ${port} | ✗ DOWN |"
        fi
    done

    echo ""
}

generate_resource_usage() {
    echo "## Использование ресурсов"
    echo ""

    local disk_usage=$(df -h / | awk 'NR==2 {print $5}')
    local disk_available=$(df -h / | awk 'NR==2 {print $4}')
    local memory_total=$(free -h | awk 'NR==2 {print $2}')
    local memory_used=$(free -h | awk 'NR==2 {print $3}')
    local container_count=$(docker ps -a --quiet 2>/dev/null | wc -l)
    local running_count=$(docker ps --quiet 2>/dev/null | wc -l)

    cat <<EOF
| Ресурс | Значение |
|--------|----------|
| Использование диска / | ${disk_usage} (доступно: ${disk_available}) |
| Память ОС | ${memory_used} / ${memory_total} |
| Всего контейнеров Docker | ${container_count} |
| Запущенных контейнеров | ${running_count} |

EOF
}

generate_footer() {
    cat <<EOF
---

**Генерирующий скрипт:** \`scripts/usage-report.sh\`
**Сохранено:** \`${REPORT_FILE}\`
EOF
}

main() {
    init

    log "Генерирую отчёт..."

    {
        generate_header
        count_active_users
        echo ""
        generate_user_activity
        generate_service_health
        generate_resource_usage
        generate_footer
    } | tee "${REPORT_FILE}"

    log "Отчёт сохранён: ${REPORT_FILE}"

    # Ротация старых отчётов
    log "Удаляю отчёты старше ${REPORT_RETENTION} дней..."
    find "${REPORT_DIR}" -maxdepth 1 -type f -name "usage_*.md" -mtime +"${REPORT_RETENTION}" -delete

    log "Завершено"
}

main "$@"
