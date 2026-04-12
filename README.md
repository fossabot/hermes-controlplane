# hermes-controlplane

Sidecar read-only para observar una instalación existente de Hermes sin tocar su código ni escribir en `~/.hermes/state.db`.

Estado actual: fase 0/1 implementada.

Incluye:
- FastAPI
- dashboard HTML mínimo server-rendered
- endpoints JSON de observabilidad
- lectura read-only de `~/.hermes/state.db`
- inventario de profiles desde `~/.hermes/profiles/*`
- estado systemd de `hermes-gateway-<profile>.service`

No incluye todavía:
- proxy OpenRouter
- budgets
- Telegram bot
- writes sobre configs de Hermes

## Principios de seguridad

- `state.db` se abre con SQLite URI `mode=ro`
- el sidecar no modifica perfiles ni servicios por su cuenta
- el mount de `~/.hermes` en Docker es read-only

## Requisitos

- Python 3.11+
- acceso local a `~/.hermes`
- systemd user services para Hermes

## Levantar localmente

```bash
cd /home/matias/hermes-controlplane
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn hermes_controlplane.main:app --host 127.0.0.1 --port 8780 --reload
```

Endpoints:
- `GET /health`
- `GET /api/profiles`
- `GET /api/profiles/{name}`
- `GET /api/sessions/recent?limit=10`
- `GET /`

## Tests

```bash
cd /home/matias/hermes-controlplane
source .venv/bin/activate
pytest -q
```

## Docker Compose

```bash
docker compose up --build
```

Por defecto expone `127.0.0.1:8780` para no depender todavía de Tailscale.

## Variables de entorno

Copia `.env.example` a `.env` si quieres cambiar rutas/host/puerto.

Variables principales:
- `HERMES_HOME=/home/matias/.hermes`
- `CONTROLPLANE_HOST=127.0.0.1`
- `CONTROLPLANE_PORT=8780`
- `CONTROLPLANE_LOG_LEVEL=info`

## TODOs siguientes

- integrar Telegram bot
- añadir `controlplane.db` propia para logs/alerts
- añadir proxy OpenRouter opt-in por profile
- añadir rollout/rollback atómico para `base_url`
- bind opcional a Tailscale cuando el host ya lo tenga instalado
