#!/usr/bin/env bash
# doctor.sh
# Диагностика здоровья платформы: 10+ проверок.
# Проверяет health-эндпоинты сервисов, живость контейнеров,
# отсутствие секретов в user-runtime, целостность томов, осиротевшие контейнеры.
#
# Использование:
#   bash scripts/doctor.sh
#   bash scripts/doctor.sh | grep FAIL  # только проблемы

set -euo pipefail

readonly HEALTH_CHECK_TIMEOUT=5
readonly DOCKER_NETWORK="hermes"  # имя docker-сети, где крутятся сервисы

# Сервисы для проверки health-эндпоинтов
declare -A HEALTH_CHECKS=(
    ["identity-proxy"]="http://127.0.0.1:8643/health"
    ["corp-dir-broker"]="http://127.0.0.1:8652/health"
    ["files-broker"]="http://127.0.0.1:8651/health"
    ["tasks-broker"]="http://127.0.0.1:8654/health"
    ["provisioner"]="http://127.0.0.1:8650/health"
)

# Секреты, которые НИКОГДА не должны быть в user-runtime
readonly -a FORBIDDEN_SECRET_PREFIXES=(
    "TELEGRAM_"
    "LLM_"
    "OPENAI_"
    "API_KEY"
)

log_check() {
    local check_name="$1"
    local result="$2"  # PASS или FAIL
    local detail="${3:-}"

    local status_str="${result}"
    if [[ "${result}" == "PASS" ]]; then
        status_str="✓ PASS"
    elif [[ "${result}" == "FAIL" ]]; then
        status_str="✗ FAIL"
    fi

    printf "%-40s %s" "[${check_name}]" "${status_str}"
    if [[ -n "${detail}" ]]; then
        echo " | ${detail}"
    else
        echo ""
    fi
}

check_health_endpoint() {
    local service_name="$1"
    local endpoint="$2"

    if curl -sf --max-time "${HEALTH_CHECK_TIMEOUT}" "${endpoint}" >/dev/null 2>&1; then
        log_check "health: ${service_name}" "PASS"
    else
        log_check "health: ${service_name}" "FAIL" "эндпоинт не отвечает: ${endpoint}"
    fi
}

check_docker_containers() {
    local running=$(docker ps --filter "status=running" --quiet 2>/dev/null | wc -l)
    local total=$(docker ps -a --quiet 2>/dev/null | wc -l)

    if [[ ${running} -gt 0 ]]; then
        log_check "docker: контейнеры запущены" "PASS" "${running}/${total} running"
    else
        log_check "docker: контейнеры запущены" "FAIL" "нет запущенных контейнеров"
    fi
}

check_user_runtime_containers() {
    local user_containers=$(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null | wc -l)
    if [[ ${user_containers} -gt 0 ]]; then
        log_check "docker: per-user runtime" "PASS" "${user_containers} контейнеров"
    else
        log_check "docker: per-user runtime" "FAIL" "ни одного user-runtime не найдено"
    fi
}

check_orphaned_containers() {
    local orphaned=0
    local orphaned_list=""

    while IFS= read -r container_id; do
        local container_name=$(docker inspect "${container_id}" --format='{{.Name}}' | sed 's/^\//')
        local has_network=$(docker inspect "${container_id}" --format='{{.HostConfig.NetworkMode}}' 2>/dev/null || echo "none")

        # TODO(REPLACE): Уточнить критерии осиротевшего контейнера в вашей топологии
        # Примеры: контейнер не подключен к основной сети, нет связи с provisioner, нет данных в логах за сутки
        if [[ "${has_network}" != "${DOCKER_NETWORK}" && "${has_network}" != "host" ]]; then
            orphaned_list="${orphaned_list}${container_name} "
            ((orphaned++))
        fi
    done < <(docker ps -a --quiet 2>/dev/null || true)

    if [[ ${orphaned} -eq 0 ]]; then
        log_check "docker: осиротевшие контейнеры" "PASS"
    else
        log_check "docker: осиротевшие контейнеры" "FAIL" "${orphaned} контейнеров: ${orphaned_list}"
    fi
}

check_volume_integrity() {
    local volumes=$(docker volume ls --quiet 2>/dev/null | wc -l)
    local unhealthy=0

    if [[ ${volumes} -gt 0 ]]; then
        while IFS= read -r volume_name; do
            # Проверяем, что том может быть проинспектирован (т.е. не повреждён)
            if ! docker volume inspect "${volume_name}" >/dev/null 2>&1; then
                ((unhealthy++))
            fi
        done < <(docker volume ls --quiet 2>/dev/null || true)
    fi

    if [[ ${unhealthy} -eq 0 ]]; then
        log_check "storage: целостность томов" "PASS" "${volumes} томов"
    else
        log_check "storage: целостность томов" "FAIL" "${unhealthy} повреждённых томов"
    fi
}

check_user_runtime_secrets() {
    local secrets_leaked=0
    local leaked_containers=""

    while IFS= read -r container_id; do
        local container_name=$(docker inspect "${container_id}" --format='{{.Name}}' | sed 's/^\//')

        # Проверяем переменные окружения контейнера на запрещённые префиксы
        for prefix in "${FORBIDDEN_SECRET_PREFIXES[@]}"; do
            if docker inspect "${container_id}" --format='{{json .Config.Env}}' 2>/dev/null | grep -q "${prefix}"; then
                leaked_containers="${leaked_containers}${container_name} "
                ((secrets_leaked++))
                break
            fi
        done
    done < <(docker ps -a --filter "name=hermes-u-" --quiet 2>/dev/null || true)

    if [[ ${secrets_leaked} -eq 0 ]]; then
        log_check "security: секреты в user-runtime" "PASS"
    else
        log_check "security: секреты в user-runtime" "FAIL" "${secrets_leaked} контейнеров с утечками: ${leaked_containers}"
    fi
}

check_docker_daemon() {
    if docker info >/dev/null 2>&1; then
        log_check "docker: daemon" "PASS"
    else
        log_check "docker: daemon" "FAIL" "daemon не отвечает"
    fi
}

check_disk_space() {
    local usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [[ ${usage} -lt 90 ]]; then
        log_check "system: место на диске" "PASS" "${usage}% использовано"
    else
        log_check "system: место на диске" "FAIL" "${usage}% использовано (критично!)"
    fi
}

check_memory_available() {
    local available=$(free -h | awk 'NR==2 {print $7}')
    log_check "system: свободная память" "PASS" "${available} доступно"
}

check_network_connectivity() {
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        log_check "network: интернет" "PASS"
    else
        log_check "network: интернет" "FAIL" "нет связи с внешней сетью"
    fi
}

main() {
    echo "=========================================="
    echo "Hermes Corp Platform — Doctor Diagnosis"
    echo "=========================================="
    echo ""

    # Базовые проверки инфраструктуры
    echo "=== Docker & Infrastructure ==="
    check_docker_daemon
    check_docker_containers
    check_user_runtime_containers
    check_orphaned_containers
    check_volume_integrity
    echo ""

    # Проверки здоровья сервисов
    echo "=== Service Health ==="
    for service_name in "${!HEALTH_CHECKS[@]}"; do
        check_health_endpoint "${service_name}" "${HEALTH_CHECKS[${service_name}]}"
    done
    echo ""

    # Проверки безопасности
    echo "=== Security ==="
    check_user_runtime_secrets
    echo ""

    # Проверки системных ресурсов
    echo "=== System Resources ==="
    check_disk_space
    check_memory_available
    check_network_connectivity
    echo ""

    echo "=========================================="
    echo "Диагностика завершена."
    echo "=========================================="
}

main "$@"
