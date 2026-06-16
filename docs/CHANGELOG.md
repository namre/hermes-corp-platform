# CHANGELOG

Журнал значительных изменений платформы Hermes Corp Platform. Только важные события: новые возможности, breaking changes, критичные баги.

**Формат**: дата (YYYY-MM-DD) в заголовке, версия (семантическое версионирование), тип события.

---

## [Unreleased]

### Added
- (Placeholder для текущей разработки)

---

## [1.0.0] — 2024-12-15

### Added
- ✓ Операционный слой: скрипты для бэкапа, idle-shutdown, health-диагностики, admin-CLI
- ✓ docs/OPERATIONS.md — обзор экспуатации (бэкапы, мониторинг, обслуживание)
- ✓ docs/OPERATIONS_RUNBOOK.md — пошаговые инструкции для операционистов
- ✓ Интеграция с cron/systemd-timer для автоматизации

### Changed
- (Изменений в API/конфиге нет)

### Fixed
- (Нет критичных багов в этом релизе)

### Deprecated
- (Ничего не объявлено устаревшим)

### Removed
- (Ничего не удалено)

### Security
- Проверка отсутствия платформенных секретов в user-runtime'ах
- Whitelist-подход для бэкапов (исключение кэшей и временных файлов)

---

## [0.9.0] — 2024-12-01

### Added
- Файловый слой (FILES.md): загрузка вложений, выдача файлов ссылкой
- Образцы блоков: Yandex360, Kaiten, LiteLLM, Hindsight
- Метод «инструкция для LLM» для быстрой адаптации брокеров

### Changed
- README.md переписан для clarity (структура, блоки, способ адаптации)
- ARCHITECTURE.md расширена (мультитенантность, память, поток запроса)

### Fixed
- Исправлена маршрутизация по Telegram ID в corp-dir-broker
- Убрана потенциальная утечка секретов через environment variables

### Security
- Isolation sandbox для user-runtime (seccomp, AppArmor примеры)
- Проверка signature Telegram webhook перед маршрутизацией

---

## [0.8.0] — 2024-11-15

### Added
- OpenWebUI интеграция: основной веб-интерфейс
- identity-proxy: резолв личности, security-детектор, форвард в runtime
- provisioner skeleton: управление per-user контейнерами

### Changed
- DEPLOYMENT.md обновлена (шаги 1-4, TLS, OpenWebUI)
- PRINCIPLES.md — принципы построения (8 принципов)

### Security
- Начальная реализация изоляции секретов в provisioner

---

## [0.7.0] — 2024-11-01

### Added
- Базовая архитектура: identity-proxy, provisioner, брокеры
- ARCHITECTURE.md: мультитенантность (контейнер на пользователя)
- Заглушки для corp-dir-broker, files-broker, tasks-broker
- Тесты на заглушках (docker compose up, curl /health)

### Security
- Концепция per-user контейнера вместо разделяемого runtime

---

## [0.1.0] — 2024-10-15

### Added
- README.md, LICENSE, .gitignore
- docker-compose.yml skeleton
- .env.example, docs/ структура
- Основная концепция: self-hosted корпоративный агент

---

## Руководство по добавлению записей

### Типы изменений (использовать в заголовках)

- **Added** — новые возможности
- **Changed** — изменения существующей функциональности
- **Deprecated** — объявления об устаревании
- **Removed** — удалённые возможности
- **Fixed** — исправления багов
- **Security** — исправления уязвимостей или улучшения безопасности

### Формат записи

```
## [X.Y.Z] — YYYY-MM-DD

### Added
- Краткое описание нового функционала (макс 1-2 строки)
- Ссылка на связанный документ, если есть: [docs/<doc>.md](docs/<doc>.md)

### Changed
- Что изменилось в API / конфигурации
- Как это влияет на пользователей / операторов

### Fixed
- Описание проблемы и решения
- Ticket/issue ID, если используется

### Security
- Уязвимость и её влияние
- Версия, в которой исправлено

```

### Примеры

**Хорошо:**
```
### Added
- Операционный слой: скрипты backup-runtimes.sh, idle-shutdown.sh, doctor.sh
- docs/OPERATIONS.md и docs/OPERATIONS_RUNBOOK.md для операторов
```

**Плохо:**
```
### Added
- Кучу всего
- Всякие изменения
```

### Версионирование

Используйте [семантическое версионирование](https://semver.org/):

- **MAJOR** (X.0.0) — breaking changes, несовместимость API
- **MINOR** (0.X.0) — новые возможности, backward-compatible
- **PATCH** (0.0.X) — bagy-fixes, backward-compatible

---

**Примечание**: Этот файл ведётся вручную. Обновляйте его при каждом значительном изменении перед/после merge в main