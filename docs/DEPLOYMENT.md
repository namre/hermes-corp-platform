# Развёртывание

## Требования

- Linux-сервер с Docker и Docker Compose.
- Образ базового агента Hermes-Agent (NousResearch) — публичный тег или ваша сборка.
- Доступ к LLM-провайдеру (OpenAI-совместимый эндпоинт: LiteLLM, OpenRouter, vLLM…).

## Шаг 1. Поднять на заглушках (10 минут)

```bash
git clone https://github.com/<you>/hermes-corp-platform
cd hermes-corp-platform
cp .env.example .env
# Заполнять секреты НЕ нужно: брокеры работают на моках.
docker compose up -d
docker compose ps
```

Проверка, что всё живо:

```bash
curl localhost:8652/health   # corp-dir-broker
curl localhost:8651/health   # files-broker
curl localhost:8654/health   # tasks-broker
curl localhost:8650/health   # provisioner
curl localhost:8643/health   # identity-proxy
```

Пробный заход (личность — заголовком; alice есть в sample_directory.json):

```bash
curl -X POST localhost:8643/v1/chat/completions \
  -H 'X-Telegram-Id: 111111111' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"привет"}]}'
# Ответ скелета: resolved_user=alice@example.com + endpoint runtime.
```

## Шаг 2. Подключить LLM и базовый агент

1. В `.env` задайте `LLM_BASE_URL` и `LLM_API_KEY`.
2. Убедитесь, что `HERMES_IMAGE` указывает на доступный образ агента.
3. В `identity-proxy/main.py` включите блок форварда (`TODO(REPLACE)`) под
   транспорт вашей сборки агента.

## Шаг 3. Заменить брокеры на реальные системы

По одному, не торопясь. Для каждого — переписываете доступ к данным в `main.py`
брокера, сохраняя эндпоинты. Подробно — [ADAPTING.md](ADAPTING.md).

## Шаг 4. Канал доступа и TLS

- Поставьте reverse-proxy (nginx/Caddy) с TLS перед `identity-proxy` (веб) и/или
  Telegram webhook.
- Личность пользователя должен подтверждать канал: подписанный Telegram webhook,
  SSO/OIDC на вебе. Не доверяйте заголовку `X-User-Email` из публичной сети.
- Пошаговая настройка OpenWebUI (подключение к proxy, проброс личности, SSO,
  чек-лист) — [../services/openwebui/README.md](../services/openwebui/README.md).

## Эксплуатация

- Бэкап томов `users/` и данных брокеров — на ваш обычный контур бэкапов.
- Автоостановка простаивающих user-runtime экономит ресурсы.
- Обновление базового агента — на отдельном стенде с прогоном smoke-тестов,
  затем выкатка с возможностью отката (pin образа по digest).
