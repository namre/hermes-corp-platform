# files-broker — каталог инструментов (образец: Yandex 360)

Заглушка покрывает минимум (upload / link / freebusy). Боевой образец на базе
Yandex 360 даёт пользователю через MCP такой набор. Используйте как чек-лист
при реализации под свой стек (Google Workspace, Microsoft 365, S3+CalDAV).

## OAuth (per-user)
| Эндпоинт | Назначение |
|---|---|
| POST /api/oauth/init | старт авторизации, отдаёт ссылку на согласие провайдера |
| POST /api/oauth/exchange | обмен code → токены, шифрование и сохранение at-rest |
| GET  /api/oauth/status | подключён ли пользователь, какие сервисы/режимы |
| POST /api/oauth/revoke | отзыв доступа |
| GET/PUT /api/preferences | режим read/write на каждый сервис |
| GET  /api/audit | журнал обращений пользователя |

## MCP-инструменты (вызывает агент)
| Сервис | Инструменты | Режимы |
|---|---|---|
| disk | upload, list, make_public_link, download | read / write |
| calendar | freebusy, list_events, create_event | read / write (CalDAV) |
| mail | list, read | read (imap_ro) / write (imap_full) |
| telemost | create_meeting | write |
| wiki | search, read_page | read |

## Что прописать в своей конфигурации
- OAuth-приложение в кабинете провайдера (для Yandex — oauth.yandex.ru):
  `client_id`, `client_secret`, redirect URI = `https://<ваш-домен>/oauth/callback`.
- Включить нужные scope в карточке приложения (иначе провайдер вернёт invalid_scope).
- Мастер-ключ шифрования токенов: `openssl rand -hex 32` → `FILES_TOKEN_MASTER_KEY`.
- Маппинг scope под режимы read/write (least privilege).
