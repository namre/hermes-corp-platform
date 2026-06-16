#!/usr/bin/env bash
# backup-runtimes.sh
# Бэкап per-user runtime с whitelist-подходом.
# Сохраняет только критичное: state.db, config.yaml, .env, personalities, plugins.
# Исключает кэши и временные файлы.
#
# Использование:
#   DRY_RUN=true bash scripts/backup-runtimes.sh      # просмотр без изменений
#   BACKUP_RETENTION_DAYS=7 bash scripts/backup-runtimes.sh  # 7 дней retention
#
# Переменные окружения:
#   BACKUP_DIR           - директория бэкапов (по умолчанию ./backups)
#   BACKUP_RETENTION_DAYS - дней хранить (по умолчанию 14)
#   DRY_RUN              - если true, показывает действия без выполнения
#   RUNTIME_ROOT         - корневая директория runtime контейнеров (по умолчанию ./users)

set -euo pipefail

readonly BACKUP_DIR="${BACKUP_DIR:-.backups}"
readonly BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
readonly DRY_RUN="${DRY_RUN:-false}"
readonly RUNTIME_ROOT="${RUNTIME_ROOT:-.users}"

readonly TIMESTAMP=$(date +%Y%m%d_%H%M%S)
readonly BACKUP_DATE=$(date +%Y-%m-%d)
readonly BACKUP_LOG="${BACKUP_DIR}/backup_${TIMESTAMP}.log"

# Whitelist критичных файлов/директорий
readonly -a BACKUP_WHITELIST=(
    "state.db"
    "config.yaml"
    ".env"
    "personalities"
    "plugins"
)

log() {
    local level="$1"
    shift
    local msg="$@"
    echo "[${level}] $(date '+%Y-%m-%d %H:%M:%S') ${msg}" | tee -a "${BACKUP_LOG}"
}

run_cmd() {
    local cmd="$@"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY_RUN" "${cmd}"
    else
        eval "${cmd}"
    fi
}

init() {
    mkdir -p "${BACKUP_DIR}"
    log "INFO" "Инициализация бэкапа"
    log "INFO" "BACKUP_DIR=${BACKUP_DIR}"
    log "INFO" "BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS}"
    log "INFO" "DRY_RUN=${DRY_RUN}"
    log "INFO" "RUNTIME_ROOT=${RUNTIME_ROOT}"
}

backup_user_runtime() {
    local user_dir="$1"
    local user_name=$(basename "${user_dir}")
    local backup_path="${BACKUP_DIR}/${BACKUP_DATE}/${user_name}_${TIMESTAMP}.tar.gz"
    local tmp_archive="/tmp/hermes_backup_${TIMESTAMP}.tar"

    log "INFO" "Бэкапирую ${user_name}..."

    # Создаём временный архив с whitelist
    mkdir -p "${BACKUP_DIR}/${BACKUP_DATE}"

    # Собираем только разрешённые файлы
    local include_args=""
    for item in "${BACKUP_WHITELIST[@]}"; do
        if [[ -e "${user_dir}/${item}" ]]; then
            include_args="${include_args} --include='${item}'"
        fi
    done

    if [[ -z "${include_args}" ]]; then
        log "WARN" "${user_name}: нет файлов для бэкапа"
        return 0
    fi

    # TODO(REPLACE): Заменить на реальный путь хранилища user-runtime, если отличается от ./users
    local cmd="tar --exclude='*' ${include_args} -czf '${backup_path}' -C '${user_dir}' . 2>/dev/null || true"
    run_cmd "${cmd}"

    if [[ "${DRY_RUN}" != "true" && -f "${backup_path}" ]]; then
        local size=$(du -h "${backup_path}" | cut -f1)
        log "OK" "${user_name}: ${size}"
    else
        log "INFO" "${user_name}: был бы создан ${backup_path}"
    fi
}

prune_old_backups() {
    log "INFO" "Удаляю старые бэкапы (старше ${BACKUP_RETENTION_DAYS} дней)..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        find "${BACKUP_DIR}" -maxdepth 2 -type f -name "*.tar.gz" -mtime +"${BACKUP_RETENTION_DAYS}" -print | while read f; do
            log "DRY_RUN" "rm '${f}'"
        done
    else
        find "${BACKUP_DIR}" -maxdepth 2 -type f -name "*.tar.gz" -mtime +"${BACKUP_RETENTION_DAYS}" -delete
        log "INFO" "Прун завершён"
    fi
}

main() {
    init

    if [[ ! -d "${RUNTIME_ROOT}" ]]; then
        log "WARN" "RUNTIME_ROOT не найден: ${RUNTIME_ROOT}"
        return 1
    fi

    # Поиск всех per-user директорий (например, user-alice, user-bob, ...)
    local user_count=0
    while IFS= read -r -d '' user_dir; do
        backup_user_runtime "${user_dir}"
        ((user_count++))
    done < <(find "${RUNTIME_ROOT}" -maxdepth 1 -type d -name "user-*" -print0 2>/dev/null || true)

    if [[ ${user_count} -eq 0 ]]; then
        log "WARN" "Не найдено per-user директорий в ${RUNTIME_ROOT}"
    else
        log "INFO" "Бэкапирован(о) ${user_count} пользователя(ей)"
    fi

    prune_old_backups

    log "INFO" "Бэкап завершён. Логи: ${BACKUP_LOG}"
}

main "$@"
