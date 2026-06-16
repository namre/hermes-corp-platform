# Сетевая модель

Все сервисы платформы слушают только на `127.0.0.1` или внутренней
docker-сети. Наружу выставляется единственная точка — reverse-proxy с TLS.
Провайдер памяти доступен только через приватный транспорт (mesh/VPN).

---

## 1. Слои сети

```
┌──────────────────────────────────────────────────────────────┐
│  ВНЕШНИЙ EDGE (публичный интернет)                           │
│                                                              │
│  clients: браузер, Telegram, мобильный                       │
│           │                                                  │
│           │  HTTPS :443 (TLS termination)                    │
│           ▼                                                  │
│  ┌─────────────────────────────┐                             │
│  │  reverse-proxy              │  nginx / Caddy              │
│  │  (единственная точка входа) │  cert: Let's Encrypt / корп │
│  └──────────────┬──────────────┘                             │
└─────────────────│────────────────────────────────────────────┘
                  │  HTTP (plain) только внутри хоста
┌─────────────────│────────────────────────────────────────────┐
│  DOCKER-СЕТЬ (hermes_internal, только 127.0.0.1 + overlay)  │
│                 │                                            │
│                 ▼                                            │
│  identity-proxy :8643                                        │
│        │            │                                        │
│        ▼            ▼                                        │
│  provisioner    hermes-u-<user> :8642  (per-user runtime)    │
│  :8650              │                                        │
│                     ├── corp-dir-broker :8652                │
│                     ├── files-broker    :8651                │
│                     ├── tasks-broker    :8654                │
│                     └── llm-gateway     :4000                │
│                                                              │
│  audit-service  :8660  (только внутри, нет наружу)          │
│                 │                                            │
│                 ▼                                            │
│  audit store  (append-only, изолированный)                   │
└─────────────────────────────────────────────────────────────-┘
                  │
                  │  приватный транспорт (mesh / VPN)
                  │  НЕ публичный интернет
┌─────────────────│────────────────────────────────────────────┐
│  ВНЕШНИЙ ПРОВАЙДЕР ПАМЯТИ (self-hosted или SaaS-подписка)    │
│                 ▼                                            │
│  memory provider  (Hindsight или совместимый)                │
│  bank: user:<id> (rw)  corp:<org> (ro)                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Таблица: что наружу, что только внутри

| Сервис / порт | Наружу (edge) | Внутри docker-сети | Примечание |
|---|---|---|---|
| reverse-proxy :443 | ДА (TLS) | — | Единственная точка входа |
| identity-proxy :8643 | нет | ДА | Только из-за proxy |
| provisioner :8650 | нет | ДА | Только из identity-proxy |
| hermes-u-* :8642 | нет | ДА | Только из provisioner / proxy |
| corp-dir-broker :8652 | нет | ДА | Только из runtime + proxy |
| files-broker :8651 | нет | ДА | Только из runtime |
| tasks-broker :8654 | нет | ДА | Только из runtime |
| llm-gateway :4000 | нет | ДА | Только из runtime |
| audit-service :8660 | нет | ДА | Только из proxy / runtime |
| audit store | нет | ДА (только audit-service) | Не доступен из runtime напрямую |
| memory provider | нет | приватный транспорт | Mesh/VPN, не публичный интернет |
| OpenWebUI :8085 | опционально через proxy | ДА | |

**Все порты** — `127.0.0.1` или docker overlay network. Прямого биндинга на
`0.0.0.0` нет ни у одного внутреннего сервиса.

---

## 3. Reverse-proxy — пример конфигурации

### Nginx (обезличенный образец)

```nginx
# /etc/nginx/sites-available/hermes
server {
    listen 443 ssl http2;
    server_name agent.example.com;

    ssl_certificate     /etc/ssl/certs/example.com.crt;
    ssl_certificate_key /etc/ssl/private/example.com.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Только identity-proxy наружу
    location / {
        proxy_pass         http://127.0.0.1:8643;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # SSE / долгие соединения
        proxy_read_timeout          300s;
        proxy_buffering             off;
    }

    # OpenWebUI (опционально, отдельный vhost или path)
    location /ui/ {
        proxy_pass http://127.0.0.1:8085/;
        proxy_set_header Host $host;
    }
}

# HTTP → HTTPS редирект
server {
    listen 80;
    server_name agent.example.com;
    return 301 https://$host$request_uri;
}
```

### Caddy (альтернатива, автоматический TLS)

```
# Caddyfile (обезличенный образец)
agent.example.com {
    reverse_proxy /ui/* localhost:8085
    reverse_proxy /* localhost:8643
}
```

---

## 4. Приватный транспорт до провайдера памяти

Трафик до внешнего провайдера памяти идёт **не через публичный интернет**.
Варианты:

| Вариант | Когда подходит |
|---|---|
| WireGuard mesh (например, Tailscale, Headscale) | Провайдер в другом облаке / VPS |
| Site-to-site VPN (IPSec / OpenVPN) | Корпоративная инфраструктура |
| Приватная сеть облачного провайдера (VPC peering) | Оба сервиса в одном облаке |
| Self-hosted в той же docker-сети | Провайдер памяти на том же хосте |

Важно: если используется WARP или аналогичный туннельный клиент — проверьте,
что он не перехватывает трафик внутренней docker-сети. Это известная точка
ошибок: WARP-клиент на хосте может перехватить запросы к `172.x.x.x` (docker),
и брокеры перестают видеть друг друга.

---

## 5. Изоляция broker-to-broker

Брокеры проверяют `BROKER_INTERNAL_AUTH` (общий секрет) на каждый входящий
запрос. Брокер отвергает запросы без валидного секрета с `401`.

```
runtime пользователя
  └─► files-broker
        x-internal-auth: <BROKER_INTERNAL_AUTH>
        X-User-Email: user@example.com
```

Секрет ротируется вместе с перезапуском стека (docker compose restart). При
смене секрета — все runtime-контейнеры пересоздаются с новым значением через
provisioner.
     