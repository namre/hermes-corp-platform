# Scripts — Операционные скрипты

Рабочие скрипты для ежедневного управления и обслуживания платформы Hermes.

## Быстрая справка

| Скрипт | Назначение | Как запускать |
|--------|-----------|---------------|
| **backup-runtimes.sh** | Бэкап per-user runtime (whitelist: state.db, config.yaml, .env, personalities, plugins). Автопруниг по retention. | `bash scripts/backup-runtimes.sh` или `DRY_RUN=true` для просмотра; `BACKUP_RETENTION_DAYS=7` для 7 дней хранения |
| **idle-shutdown.sh** | Поиск и остановка простаивающих контейнеров (>N дней неактивности). Данные сохраняются; provisioner перезапустит при необходимости. | `bash scripts/idle-shutdown.sh` или `IDLE_DAYS=3` для 3 дней неактивности; `DRY_RUN=true` для просмотра |
| **doctor.sh** | Диагностика здоровья: health-эндпоинты сервисов, живость контейнеров, отсутствие секретов в user-runtime, целостность томов, дисковое пространство. 10+ проверок. | `bash scripts/doctor.sh` — показывает PASS/FAIL по каждому пункту |
| **admin-cli.sh** | Управление пользователями: list (с idle-статусом), restart-user, restart-all, user-config. | `bash scripts/admin-cli.sh list`, `bash scripts/admin-cli.sh restart-user alice@example.com`, `bash scripts/admin-cli.sh help` |
| **usage-report.sh** | Анализ активности на основе логов Docker. Markdown-отчёт по пользователям, health сервисов, ресурсам. Ротация за 90 дней. | `bash scripts/usage-report.sh > report.md` или `LOG_LOOKBACK_HOURS=48` для 48 часов истории |

## Переменные окружения

### Общие
- `DRY_RUN=true` — показывает действия без выполнения (поддерживают backup-runtimes.sh, idle-shutdown.sh)

### backup-runtimes.sh
- `BACKUP_DIR` — директория сохранения бэкапов (по умолчанию `.backups`)
- `BACKUP_RETENTION_DAYS` — дней хранить бэкапы (по умолчанию 14)
- `RUNTIME_ROOT` — корневая директория user-runtime (по умолчанию `.users`)

### idle-shutdown.sh
- `IDLE_DAYS` — дней неактивности перед остановкой (по умолчанию 7)

### admin-cli.sh
- `PROVISIONER_URL` — URL provisioner API (по умолчанию `http://127.0.0.1:8650`)
- `IDLE_DAYS` — для команды `list --idle` (по умолчанию 3)

### usage-report.sh
- `REPORT_DIR` — директория отчётов (по умолчанию `.reports`)
- `REPORT_RETENTION` — дней хранить отчёты (по умолчанию 90)
- `LOG_LOOKBACK_HOURS` — часов истории для анализа (по умолчанию 24)

## Примеры использования

### Ежедневный бэкап с 14-дневной ротацией
```bash
bash scripts/backup-runtimes.sh
```

### Просмотр действий перед выполнением
```bash
DRY_RUN=true bash scripts/backup-runtimes.sh
```

### Остановка неактивных пользователей
```bash
bash scripts/idle-shutdown.sh
```

### Быстрая диагностика
```bash
bash scripts/doctor.sh
```

### Список всех пользователей с idle-статусом
```bash
bash scripts/admin-cli.sh list --idle
```

### Рестарт одного пользователя
```bash
bash scripts/admin-cli.sh restart-user alice@example.com
```

### Генерирование weekly-отчёта
```bash
bash scripts/usage-report.sh > weekly_report.md
```

## Интеграция с cron/systemd-timer

### Пример crontab (бэкап каждый день в 02:00, idle-shutdown в 03:00, диагностика каждый час)
```cron
0 2 * * * cd /path/to/hermes-corp-platform && BACKUP_RETENTION_DAYS=14 bash scripts/backup-runtimes.sh >> .backups/cron.log 2>&1
0 3 * * * cd /path/to/hermes-corp-platform && IDLE_DAYS=7 bash scripts/idle-shutdown.sh >> /var/log/hermes/idle-shutdown.log 2>&1
0 * * * * cd /path/to/hermes-corp-platform && bash scripts/doctor.sh > /tmp/hermes_health.txt 2>&1
```

### Пример systemd-timer для бэкапа (создать `/etc/systemd/system/hermes-backup.service`)
```ini
[Unit]
Description=Hermes Backup Runtime
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/path/to/hermes-corp-platform
ExecStart=/bin/bash -c 'BACKUP_RETENTION_DAYS=14 bash scripts/backup-runtimes.sh'
StandardOutput=journal
StandardError=journal
```

И таймер (`/etc/systemd/system/hermes-backup.timer`):
```ini
[Unit]
Description=Daily Hermes Backup
Requires=hermes-backup.service

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Включить:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-backup.timer
sudo systemctl start hermes-backup.timer
```

## Мониторинг и логирование

- **backup-runtimes.sh** логирует в `.backups/backup_TIMESTAMP.log`
- **idle-shutdown.sh** выводит в stdout (перенаправляйте в нужный лог)
- **doctor.sh** пишет в stdout (удобно для cron-email)
- **usage-report.sh** сохраняет в `.reports/usage_TIMESTAMP.md`

## Рекомендации

1. **Бэкапы**: запускайте ежедневно (например, 02:00). 14-дневная retention по умолчанию. Проверяйте место на диске.
2. **Idle-shutdown**: запускайте раз в сутки (например, 03:00) для экономии ресурсов. Контейнеры будут пересозданы provisioner'ом.
3. **doctor.sh**: запускайте каждый час для мониторинга. Парсьте вывод на FAIL для оповещений.
4. **admin-cli.sh**: интерактивный инструмент; для скриптов используйте provisioner API напрямую.
5. **usage-report.sh**: еженедельно для обзора активности; сохраняйте в версионированное хранилище (git, S3).

## Замены и расширения (TODO)

Все скрипты содержат комментарии `TODO(REPLACE)` в местах, где нужна адаптация под реальную инфраструктуру:

- **backup-runtimes.sh**: `RUNTIME_ROOT` и путь хранилища user-runtime
- **idle-shutdown.sh**: источник `last_seen` (docker inspect, provisioner API или .last_seen файл)
- **doctor.sh**: критерии осиротевшего контейнера, источник секретов для проверки
- **admin-cli.sh**: provisioner API endpoints, алгоритм slug↔email, чтение конфига
- **usage-report.sh**: парсинг логов, де-slug email, версионирование отчётов

См. подробнее в [docs/OPERATIONS.md](../docs/OPERATIONS.md) и [docs/OPERATIONS_RUNBOOK.md](../docs/OPERATIONS_RUNBOOK.md).
