# BUGS — Известные проблемы и ограничения

Журнал известных багов платформы Hermes Corp Platform. Отслеживание: ID, severity, описание, статус.

**Формат**: `BUG-NNN` (номер), severity (CRITICAL / HIGH / MEDIUM / LOW), дата открытия, статус (open / in_progress / fixed).

---

## Активные баги

### BUG-001: Idle-shutdown неточный источник last_seen

**Severity**: MEDIUM  
**Opened**: 2024-12-15  
**Status**: open  

**Описание**:  
Скрипт `idle-shutdown.sh` использует `docker inspect StartedAt` для определения времени последней активности. Это примерное значение — контейнер может быть рестартован provisioner'ом, но это не означает, что пользователь был активен.

**Симптомы**:
- Активный пользователь может быть остановлен, если provisioner ненадолго рестартовал контейнер
- Простаивающие пользователи могут остаться running, если контейнер был запущен давно

**Решение**:
Использовать более точный источник `last_seen`:
- Provisioner API для получения timestamp последнего запроса пользователя
- Или .last_seen файл, обновляемый при каждом обращении
- Или логирование в provisioner с API /stats/<email>

**Ссылка**: [scripts/idle-shutdown.sh](../scripts/idle-shutdown.sh#L58)

---

### BUG-002: Утечка секретов при копировании конфига

**Severity**: HIGH  
**Opened**: 2024-12-15  
**Status**: open  

**Описание**:  
При создании user-runtime provisioner может скопировать платформенные секреты (LLM_API_KEY, TELEGRAM_TOKEN) из .env в environment variables контейнера. Хотя изоляция в provisioner должна это предотвратить, потребуется audit скрипт для проверки.

**Симптомы**:
- `docker inspect hermes-u-alice --format='{{json .Config.Env}}'` показывает LLM_* или TELEGRAM_* переменные
- health-check doctor.sh выдаёт FAIL на security check

**Решение**:
- Provisioner должен иметь whitelist ENV переменных, разрешённых для user-runtime
- Все остальные переменные игнорируются
- doctor.sh всегда проверяет отсутствие forbidden prefixes

**Ссылка**: [scripts/doctor.sh#check_user_runtime_secrets](../scripts/doctor.sh#L137-L165)

---

### BUG-003: Per-user контейнер может потребить все ресурсы хоста

**Severity**: HIGH  
**Opened**: 2024-12-10  
**Status**: open  

**Описание**:  
User-runtime контейнер может войти в infinite loop или потребить все CPU/RAM хоста без лимитов. Дефолтные лимиты в docker-compose.yml не установлены.

**Симптомы**:
- `docker stats` показывает контейнер с 100% CPU или 95%+ памяти
- Другие сервисы становятся неотзывчивыми или перезагружаются

**Решение**:
- В docker-compose.yml установить `deploy.resources.limits` для `hermes-u-*` сервисов
- Типичные лимиты: 2GB RAM, 2 CPU для production
- Мониторить в prometheus/datadog и алертить при превышении 80%

**Пример**:
```yaml
services:
  hermes-u-template:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

---

### BUG-004: Бэкап может содержать .env с реальными секретами

**Severity**: CRITICAL  
**Opened**: 2024-12-15  
**Status**: open  

**Описание**:  
Если в user-runtime .env содержатся секреты (что не должно быть, см. BUG-002), они попадут в бэкап archive (.backups/). Таким образом, бэкап-архив становится чувствительным к доступу.

**Симптомы**:
- `tar -tzf .backups/alice_*.tar.gz | grep .env` показывает файл
- `tar -xzf .backups/alice_*.tar.gz -O .env | grep LLM_` показывает секрет

**Решение**:
- Убедиться, что provisioner не кладёт платформенные секреты в user-runtime (см. BUG-002)
- Или дополнительно фильтровать .env при архивировании (удалять forbidden prefixes)
- Бэкап-архивы хранить с ограниченными правами доступа (600)

**Ссылка**: [scripts/backup-runtimes.sh#backup_user_runtime](../scripts/backup-runtimes.sh#L54-L73)

---

### BUG-005: Осиротевшие контейнеры не очищаются автоматически

**Severity**: MEDIUM  
**Opened**: 2024-12-10  
**Status**: open  

**Описание**:  
Если provisioner аварийно завершится, может остаться контейнер, который не подключен ни к какой сети или забыт. Doctor.sh его обнаружит, но удаления не произойдёт.

**Симптомы**:
- `bash scripts/doctor.sh` выдаёт FAIL на проверке осиротевших контейнеров
- `docker ps -a` показывает контейнер без родительского provisioner entry

**Решение**:
- Добавить команду в doctor.sh для автоочистки (с dry-run опцией)
- Или периодический cron-job для `docker container prune`

**Ссылка**: [scripts/doctor.sh#check_orphaned_containers](../scripts/doctor.sh#L128-L147)

---

## Закрытые баги

### BUG-006: Telegram webhook signature validation missing ✓

**Severity**: CRITICAL  
**Opened**: 2024-11-30  
**Status**: fixed ✓

**Описание**:  
В примере Telegram интеграции не было проверки подписи webhook.

**Решение**:  
Добавлена проверка HMAC в identity-proxy. Все входящие Telegram запросы должны быть подписаны правильно.

**Fixed in**: v1.0.0

---

## Рекомендации

1. **Мониторить CRITICAL баги** — требуют срочного решения перед production-выкаткой
2. **HIGH баги** — решить перед выкаткой в основной окружение; для dev может быть отложено
3. **MEDIUM/LOW** — планировать в спринте, но не блокирует выкатку

## Версионирование багов

- **Локальный git**: используйте ветку `bugfix/BUG-NNN` для исправления
- **Связь с CHANGELOG.md**: при закрытии баги добавить запись в раздел `[Fixed]`
- **Тестирование**: после исправления добавить unit/integration тест, чтобы баг не повторился

---

**Назад**: [docs/CHANGELOG.md](CHANGELOG.md) — историяверсий.
