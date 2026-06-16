# Runbook — критические операции

Пошаговые инструкции для типичных операционных задач. Предназначен для операторов платформы.

## Обновление базового агента (Hermes-Agent)

### Сценарий

Вышла новая версия Hermes-Agent (например, bugfix). Нужно обновить образ без потери данных пользователей.

### Процесс

1. **Подготовка**
   ```bash
   # Зафиксировать текущий образ по digest (что сейчас running)
   CURRENT_DIGEST=$(docker inspect hermes-agent:latest --format='{{index .RepoDigests 0}}' | cut -d'@' -f2)
   echo "Current digest: ${CURRENT_DIGEST}"
   
   # Сохранить для отката
   echo "${CURRENT_DIGEST}" > .backup_image_digest
   ```

2. **Подготовка нового образа**
   ```bash
   # Скачать новый образ с явным тегом версии
   docker pull hermes-agent:v1.2.3
   
   # Убедиться, что образ работает (базовый smoke-test)
   docker run --rm hermes-agent:v1.2.3 python3 -c "import hermes; print('OK')"
   ```

3. **Smoke-тест на отдельном стенде** (если есть)
   ```bash
   # На dev/staging поднять с новым образом
   HERMES_IMAGE=hermes-agent:v1.2.3 docker-compose -f docker-compose.test.yml up -d
   
   # Прогнать базовые тесты
   curl -X POST http://127.0.0.1:8643/v1/chat/completions \
     -H 'X-Telegram-Id: 111111111' \
     -H 'Content-Type: application/json' \
     -d '{"messages":[{"role":"user","content":"привет"}]}'
   
   # Убедиться, что ответ корректен и нет ошибок
   # Затем остановить
   docker-compose -f docker-compose.test.yml down
   ```

4. **Выкатка в production**
   ```bash
   # Обновить .env (или docker-compose.yml)
   sed -i 's|HERMES_IMAGE=.*|HERMES_IMAGE=hermes-agent:v1.2.3|' .env
   
   # Pull новый образ на production-хосте
   docker pull hermes-agent:v1.2.3
   
   # Рестартить только admin-агента (не трогаем user-runtime'ы)
   docker-compose restart hermes-agent
   
   # Проверить, что запустился
   docker ps | grep hermes-agent
   
   # Проверить health
   curl http://127.0.0.1:8642/health
   ```

5. **Обновление user-runtime'ов** (постепенно)
   ```bash
   # Способ 1: остановить все контейнеры, provisioner переоздаст с новым образом
   bash scripts/idle-shutdown.sh  # остановить неактивных
   bash scripts/admin-cli.sh restart-all  # остановить активных
   
   # Provisioner поднимет новые контейнеры с образом из .env
   
   # Способ 2: постепенная выкатка (если пользователей много)
   # Примечание: требует доработки provisioner API для graceful rolling update
   ```

6. **Проверка после обновления**
   ```bash
   # Убедиться, что новые user-runtime'ы работают
   bash scripts/doctor.sh | grep -E "(FAIL|health)"
   
   # Проверить логи ошибок
   for c in $(docker ps -a --filter "name=hermes-u-" --quiet | head -5); do
     docker logs --tail 20 "${c}" | grep -i error || echo "OK: $(docker inspect $c --format='{{.Name}}')"
   done
   ```

### Откат

Если что-то пошло не так:

```bash
# Прочитать сохранённый digest
OLD_DIGEST=$(cat .backup_image_digest)

# Вернуться к старому образу
HERMES_IMAGE="hermes-agent@${OLD_DIGEST}" docker-compose restart hermes-agent

# Остановить новые user-runtime'ы, provisioner переоздаст со старым образом
bash scripts/admin-cli.sh restart-all

# Проверить
bash scripts/doctor.sh
```

## Restore из бэкапа

### Сценарий

Пользователь случайно удалил важные данные, или контейнер сломался. Нужно восстановить из бэкапа.

### Процесс

1. **Найти нужный бэкап**
   ```bash
   # Список всех бэкапов пользователя
   ls -lt .backups/**/alice*.tar.gz
   
   # Выбрать нужный (например, самый свежий перед проблемой)
   BACKUP=".backups/2024-12-15/alice_20241215_023045.tar.gz"
   ```

2. **Остановить контейнер**
   ```bash
   docker stop hermes-u-alice 2>/dev/null || true
   docker wait hermes-u-alice 2>/dev/null || true
   ```

3. **Очистить runtime и restore**
   ```bash
   USER_DIR=".users/user-alice"
   
   # Backup текущего состояния (на случай, если что-то пошло не так)
   mkdir -p .users/backups
   tar -czf ".users/backups/user-alice_before_restore_$(date +%s).tar.gz" "${USER_DIR}"
   
   # Очистить whitelist-файлы
   rm -f "${USER_DIR}/state.db" "${USER_DIR}/config.yaml" "${USER_DIR}/.env"
   rm -rf "${USER_DIR}/personalities" "${USER_DIR}/plugins"
   
   # Распаковать бэкап
   tar -xzf "${BACKUP}" -C "${USER_DIR}"
   
   # Проверить права
   ls -la "${USER_DIR}"
   ```

4. **Перезапустить контейнер**
   ```bash
   # Provisioner поднимет контейнер при следующем запросе, или явно:
   # TODO(REPLACE): API provisioner'а для рестарта
   docker start hermes-u-alice 2>/dev/null || docker-compose up -d hermes-u-alice
   
   # Проверить логи
   docker logs --tail 50 hermes-u-alice | tail -20
   ```

5. **Валидация**
   ```bash
   # Убедиться, что данные вернулись
   curl -X POST http://127.0.0.1:8643/v1/chat/completions \
     -H 'X-Telegram-Id: 111111111' \
     -H 'Content-Type: application/json' \
     -d '{"messages":[{"role":"user","content":"какая была последняя задача?"}]}'
   ```

## Рестарт одного пользователя (без потери данных)

### Сценарий

User-runtime зависает или требует рестарта для применения новой конфигурации.

### Процесс

```bash
# Способ 1: через admin-cli (рекомендуется)
bash scripts/admin-cli.sh restart-user alice@example.com

# Способ 2: вручную
EMAIL="alice@example.com"
SLUG=$(echo "${EMAIL}" | sed 's/@.*//' | tr '[:upper:]' '[:lower:]')
CONTAINER="hermes-u-${SLUG}"

# Остановить
docker stop "${CONTAINER}"

# Provisioner поднимет заново (или явно)
docker-compose up -d "${CONTAINER}"

# Проверить
docker logs --tail 30 "${CONTAINER}"
```

Данные пользователя **сохраняются** (тома остаются).

## Рестарт всех user-runtime'ов

### Сценарий

Накатилось обновление конфигурации, которое требует перезапуска всех контейнеров.

### Процесс

```bash
bash scripts/admin-cli.sh restart-all

# Или вручную
docker-compose stop hermes-u-* 2>/dev/null || true
docker-compose up -d

# Провести health-check
bash scripts/doctor.sh | head -20
```

**Внимание**: все пользователи будут отключены на время перезапуска (~10-30 сек на контейнер).

## Диагностика проблемы

### Контейнер не запускается

```bash
CONTAINER="hermes-u-alice"

# 1. Проверить логи
docker logs "${CONTAINER}"

# 2. Инспект контейнера
docker inspect "${CONTAINER}" | grep -A 5 '"State"'

# 3. Проверить диск (может быть переполнен)
docker run --rm -it -v hermes-data:/data alpine du -sh /data

# 4. Проверить права доступа на тома
docker run --rm -it -v "hermes-u-alice:/runtime" alpine ls -la /runtime
```

### Сервис не отвечает на health-check

```bash
# 1. Проверить, запущен ли
docker ps | grep <service_name>

# 2. Проверить логи
docker logs <service_container>

# 3. Проверить конфигурацию (например, .env)
docker inspect <service_container> --format='{{json .Config.Env}}' | grep -o '"[^"]*"' | head -20

# 4. Попробовать health-endpoint вручную (может быть firewall)
docker exec <service_container> curl -s http://127.0.0.1:<port>/health || echo "FAIL"
```

### Утечка памяти в user-runtime

```bash
# Мониторить память контейнера
watch 'docker stats hermes-u-alice --no-stream'

# Посмотреть процессы внутри
docker top hermes-u-alice

# Если OOMKilled — либо лимит стоит маленький, либо реальная утечка
docker inspect hermes-u-alice --format='{{json .HostConfig.Memory}}'
```

## Эскалация

Если вы не можете решить проблему:

1. Собрать диагностику:
   ```bash
   bash scripts/doctor.sh > /tmp/doctor_report.txt
   docker-compose ps > /tmp/docker_ps.txt
   docker logs hermes-agent > /tmp/hermes_agent.log
   docker logs identity-proxy > /tmp/identity_proxy.log
   ```

2. Обратиться в команду разработки с логами и описанием проблемы.

---

**Назад**: [docs/OPERATIONS.md](OPERATIONS.md) — обзор операционного управления.
