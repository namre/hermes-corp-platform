# OpenWebUI — настройка интерфейса

Что именно выставить и куда вставить, чтобы OpenWebUI стал интерфейсом платформы.
Часть задаётся переменными в `docker-compose.yml`, часть — в самом OpenWebUI
(Admin Panel), если вы не прокидываете это через env.

## 1. Подключение к платформе (обязательно)

OpenWebUI должен ходить к моделям не напрямую к провайдеру, а **через
identity-proxy**. Это и делает его частью платформы.

| Переменная (в compose) | Значение | Зачем |
|---|---|---|
| `OPENAI_API_BASE_URL` | `http://identity-proxy:8643/v1` | весь трафик идёт в proxy, а не к провайдеру напрямую |
| `OPENAI_API_KEY` | `${HERMES_API_KEY}` | ключ, которым proxy принимает запросы |
| `ENABLE_FORWARD_USER_INFO_HEADERS` | `true` | **ключевая** настройка: пробрасывает личность вошедшего в proxy |
| `WEBUI_AUTH` | `true` | вход обязателен (иначе личности нет) |

То же самое **можно сделать в интерфейсе**, если не через env:
**Admin Panel → Settings → Connections → OpenAI API**: URL = `http://identity-proxy:8643/v1`,
ключ = ваш `HERMES_API_KEY`. Env-способ предпочтительнее — конфиг в коде, не в БД.

## 2. Проброс личности (как proxy узнаёт, кто пишет)

При `ENABLE_FORWARD_USER_INFO_HEADERS=true` OpenWebUI добавляет к каждому
upstream-запросу заголовки вошедшего пользователя:

```
X-OpenWebUI-User-Email   <-- этот читает identity-proxy
X-OpenWebUI-User-Name
X-OpenWebUI-User-Id
X-OpenWebUI-User-Role
```

`identity-proxy` берёт `X-OpenWebUI-User-Email`, находит сотрудника в
`corp-dir-broker` и роутит в его персональный runtime. Ничего вставлять
вручную не нужно — только включить флаг.

> ⚠️ Безопасность: раз личность приходит заголовком, **proxy должен быть
> доступен только из OpenWebUI** (внутренняя docker-сеть, порт на `127.0.0.1`).
> Если proxy торчит наружу — кто угодно подставит чужой email. Снаружи
> выставляется только сам OpenWebUI за reverse-proxy с TLS.

## 3. Аутентификация пользователей (выбрать одно)

Личности можно доверять ровно настолько, насколько надёжен вход в OpenWebUI.

- **SSO/OIDC (рекомендуется для прода).** Подключите корпоративный провайдер,
  чтобы email был подтверждён. Переменные семейства `OAUTH_*` /
  `ENABLE_OAUTH_SIGNUP` — см. документацию OpenWebUI. Это и есть «REPLACE: ваш
  SSO» из compose.
- **Локальные логины (для пилота).** `WEBUI_AUTH=true`, регистрация под
  контролем: `ENABLE_SIGNUP=false` и заводите пользователей вручную, либо
  `ENABLE_SIGNUP=true` + `DEFAULT_USER_ROLE=pending` с ручным одобрением.

Важно: email в OpenWebUI должен совпадать с email в каталоге сотрудников
(`corp-dir-broker`) — по нему идёт резолв.

## 4. Модель

`identity-proxy`/агент сами определяют модель (через единый `llm-gateway`),
поэтому пользователю не нужно выбирать провайдера. Если в выпадашке моделей
пусто — проверьте, что соединение из п.1 поднялось и `llm-gateway` отвечает.
При желании зафиксируйте одну модель в proxy (вариант `FORCE_CHAT_MODEL`), чтобы
выбор в UI не влиял на маршрутизацию.

## 5. Публичный доступ (прод)

- Reverse-proxy (nginx/Caddy) с TLS перед OpenWebUI; `WEBUI_URL` = публичный адрес.
- Наружу — только OpenWebUI. `identity-proxy`, брокеры, gateway — внутри сети.

## 6. Файловый роутер (загрузка/выдача файлов)

Чтобы вложения попадали в персональный runtime, а созданные агентом файлы
показывались ссылкой, поставьте функцию-фильтр **Corp File Router**:

1. **Admin Panel → Functions → +** (Import / New Function).
2. Вставьте код `services/openwebui/file_router.py`, сохраните, включите.
3. В **Valves** функции задайте:
   - `proxy_files_url` / `proxy_register_url` / `proxy_download_base` — по
     умолчанию указывают на internal `identity-proxy` (менять не нужно, если
     имена сервисов те же);
   - `client_api_key` = ваш `HERMES_API_KEY` (тот же, что у OpenWebUI-соединения).
4. Проверьте: приложите файл в чат (статус «📤 Передаю…»), затем попросите агента
   сгенерировать файл — в ответе должна появиться ссылка на скачивание, а не путь.

Как это работает и контракт эндпоинтов — [../../docs/FILES.md](../../docs/FILES.md).

## Чек-лист

- [ ] `OPENAI_API_BASE_URL` указывает на `identity-proxy`, не на провайдера
- [ ] `OPENAI_API_KEY` = `HERMES_API_KEY`
- [ ] `ENABLE_FORWARD_USER_INFO_HEADERS=true`
- [ ] `WEBUI_AUTH=true` + выбран способ входа (SSO для прода)
- [ ] email в OpenWebUI == email в `corp-dir-broker`
- [ ] proxy не доступен из публичной сети
- [ ] наружу выставлен только OpenWebUI за TLS
- [ ] установлена функция Corp File Router, в Valves задан `client_api_key`
