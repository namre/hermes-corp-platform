# provisioner

Создаёт и обслуживает по одному контейнеру-агенту на пользователя.

## Что делает

1. **`strip_platform_env()`** — вырезает секреты платформы из окружения user-runtime.
   Даже если пользователь уговорит агента напечатать `printenv` — токена бота
   и мастер-ключей там не будет.

2. **`_fake_telegram_token(runtime_id)`** — генерирует per-user fake-токен
   для Telegram MUX-прокси. Настоящий `TELEGRAM_BOT_TOKEN` (@BotFather) в
   us