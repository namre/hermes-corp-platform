# corp-dir-broker (заглушка)

Каталог сотрудников: «кто это», роли, маппинг Telegram↔email, оргструктура.
`identity-proxy` спрашивает у него, какому пользователю принадлежит входящий
Telegram ID или email.

**Заменить на своё:** перепишите `load_directory()` в `main.py` под ваш
HRIS / LDAP / AD / HR-портал. Сохраните эндпоинты и формат полей
(`email`, `full_name`, `position`, `org_unit`, `telegram_id`, `manager_email`).
