# Hermes Control Plane — PRD Final Consolidado

**Host objetivo**: knidian-monitoring (Ubuntu 24.04, user: matias)
**Fecha**: 2026-04-12
**Estado**: Aprobado para implementación

---

## 1. Resumen Ejecutivo

Hermes Control Plane es un sidecar aislado que observa, controla y hace proxy de las instancias de Hermes corriendo como servicios systemd de usuario en `knidian-monitoring`. Opera como proceso independiente (contenedor Docker Compose) que nunca modifica el runtime de Hermes directamente — su único punto de escritura sobre Hermes es el campo `base_url` en la config de perfil, bajo comando explícito del operador y con backup atómico.

El sistema se despliega en capas incrementales: primero observación pura (read-only), luego proxy opt-in por perfil con tracking de costos y killswitch, y finalmente flags de anomalía simples. Cada capa puede activarse o revertirse de forma independiente sin afectar las demás.

La interfaz principal de operaciones es un bot de Telegram. Se complementa con un dashboard web ligero (HTMX + Jinja2).

---

## 2. Objetivos, No-Objetivos y Principios Rectores

### Objetivos

- **O1**: Visibilidad completa del estado de todos los perfiles Hermes (sesiones, mensajes, estado systemd, config).
- **O2**: Control operacional vía Telegram: pause, resume, kill por perfil.
- **O3**: Proxy transparente de requests a OpenRouter con tracking de costos por perfil y presupuestos configurables.
- **O4**: Alertas proactivas a Telegram ante anomalías simples (gasto excesivo, sesión muy larga, rate de mensajes alto).
- **O5**: Rollout y rollback atómico por perfil, sin downtime de Hermes.

### No-Objetivos

- **NO1**: Modificar el código fuente de Hermes.
- **NO2**: Soportar múltiples hosts o despliegue SaaS.
- **NO3**: Loop detection inteligente o análisis semántico de conversaciones (fuera del MVP).
- **NO4**: Soportar providers distintos de OpenRouter para cost tracking.
- **NO5**: Reemplazar la CLI de Hermes — el control plane complementa, no sustituye.
- **NO6**: Scheduler de perfiles (post-MVP, v0.4+).
- **NO7**: Replay de sesiones (post-MVP, v0.4+).

### Principios Rectores

1. **Read-only first**: `state.db` de Hermes es SIEMPRE de solo lectura. Sin excepciones.
2. **Sidecar aislado**: el control plane no comparte proceso ni memoria con Hermes. Si el sidecar muere, Hermes sigue intacto.
3. **Opt-in per profile**: ningún perfil pasa por el proxy hasta que el operador lo active explícitamente.
4. **Rollback atómico**: cada cambio sobre config de perfil genera backup previo. Revertir es un solo comando.
5. **Python-first**: sin Node, sin build steps, sin dependencias pesadas.
6. **Telegram-first**: toda operación crítica debe ser ejecutable desde Telegram.

---

## 3. Arquitectura Final Propuesta

```
┌─────────────────────────────────────────────────────────┐
│                   knidian-monitoring                      │
│                                                          │
│  ┌──────────────────────┐    ┌────────────────────────┐  │
│  │   Hermes (systemd)   │    │  Control Plane (Docker) │  │
│  │                      │    │                         │  │
│  │  hermes-gateway-*.   │    │  FastAPI (uvicorn)      │  │
│  │  service             │    │    ├── API REST          │  │
│  │                      │    │    ├── Dashboard HTMX    │  │
│  │  ~/.hermes/          │    │    ├── Proxy OpenRouter  │  │
│  │    config.yaml  ◄────┼────┼──  │   (reverse proxy)  │  │
│  │    state.db (RO) ────┼────┼──► │                    │  │
│  │    profiles/    ◄────┼────┼──  ├── Bot Telegram      │  │
│  │                      │    │    │   (long-polling)    │  │
│  └──────────────────────┘    │    └────────────────────│  │
│                              │                         │  │
│                              │  controlplane.db (RW)   │  │
│                              │    ├── cost_events      │  │
│                              │    ├── budgets          │  │
│                              │    ├── alerts_log       │  │
│                              │    ├── proxy_log        │  │
│                              │    └── config_backups   │  │
│                              └────────────────────────────┘  │
│                                                          │
│           ──── = read-only    ◄── = write (backup+swap)  │
└─────────────────────────────────────────────────────────┘
```

### Componentes

| Componente | Tecnología | Responsabilidad |
|---|---|---|
| **API REST** | FastAPI + uvicorn | Endpoints de estado, control, configuración |
| **Dashboard** | HTMX + Jinja2 (servido por FastAPI) | Visualización de estado, costos, sesiones |
| **Proxy OpenRouter** | httpx (async reverse proxy) | Intercepta requests, extrae costos de `usage`, aplica budgets y killswitch |
| **Bot Telegram** | python-telegram-bot (long-polling) | Interfaz de ops: estado, pause/resume/kill, alertas, reportes de costos |
| **Observer** | aiosqlite (read-only a state.db) | Lee sesiones, mensajes, estado de perfiles |
| **Systemd Monitor** | subprocess/dbus | Lee estado de services `hermes-gateway-*.service` |
| **Storage propio** | SQLite (`controlplane.db`, read-write) | Costos, budgets, logs de proxy, backups de config |
| **Alerting** | Python nativo → Telegram | Evalúa thresholds simples, envía alertas directas |

### Stack técnico

- Python 3.12+
- FastAPI, uvicorn
- httpx (async HTTP client para proxy)
- aiosqlite (acceso async a SQLite)
- python-telegram-bot
- Jinja2, HTMX (dashboard)
- Docker Compose (single container)

### Memoria objetivo

- **512 MB** RAM máximo para el contenedor completo.

---

## 4. Modelo Operacional

### 4.1 Observación (Layer 0 — siempre activo)

Lee de `~/.hermes/state.db` en modo read-only:
- Sesiones activas por perfil (tabla `sessions`)
- Mensajes recientes (tabla `messages`, búsqueda FTS via `messages_fts*`)
- Estado systemd de cada service (`systemctl --user status hermes-gateway-*.service`)
- Configuración activa de cada perfil (`~/.hermes/profiles/*/`)
- Configuración global (`~/.hermes/config.yaml`)

**Frecuencia de polling**: cada 30 segundos para estado systemd, cada 60 segundos para state.db.

### 4.2 Control (Layer 0 — comandos explícitos)

Acciones sobre perfiles Hermes, ejecutables desde Telegram o API:

| Acción | Mecanismo | Reversible |
|---|---|---|
| **Pause** (soft) | Proxy retorna 503 para el perfil | Sí — resume |
| **Resume** | Proxy deja pasar requests | Inmediato |
| **Kill** (hard) | `systemctl --user stop hermes-gateway-{profile}.service` | Sí — start |
| **Start** | `systemctl --user start hermes-gateway-{profile}.service` | — |
| **Restart** | `systemctl --user restart hermes-gateway-{profile}.service` | — |

**Pause vs Kill**: Pause es un soft-stop a nivel proxy (Hermes sigue vivo pero no puede llamar al LLM). Kill detiene el proceso entero. Pause requiere que el perfil tenga proxy activo.

### 4.3 Proxy OpenRouter (Layer 1 — opt-in per profile)

Reverse proxy async (httpx) que intercepta requests a OpenRouter:

1. **Activación**: operador ejecuta comando Telegram/API → control plane escribe `base_url` en la config del perfil apuntando al proxy local → reinicia el service.
2. **Backup**: antes de modificar config, se copia el archivo original a `controlplane.db.config_backups` con timestamp.
3. **Passthrough**: el proxy reenvía el request a OpenRouter, espera la response, extrae `usage` del body, registra el costo en `controlplane.db.cost_events`.
4. **Killswitch**: si el budget del perfil se agota, el proxy retorna 503 con body explicativo. Alerta a Telegram.
5. **Desactivación/Rollback**: restaura `base_url` original desde backup, reinicia service.

### 4.4 Budgets y Costos

- Costos extraídos del campo `usage` en responses de OpenRouter (tokens in/out × precio del modelo).
- Granularidad: por perfil, por día, por mes.
- Presupuestos configurables por perfil: diario y mensual.
- Acciones al alcanzar budget: alerta (80%), killswitch automático (100%), o solo alerta (configurable).
- Tabla `cost_events`: `(id, profile, model, tokens_in, tokens_out, cost_usd, timestamp)`.
- Tabla `budgets`: `(profile, period, limit_usd, action_on_limit)`.

### 4.5 Alertas (Telegram)

Alertas simples basadas en thresholds, evaluadas en cada ciclo de polling:

| Alerta | Condición | Severidad |
|---|---|---|
| Budget warning | Gasto perfil ≥ 80% del budget | WARNING |
| Budget exceeded | Gasto perfil ≥ 100% del budget | CRITICAL |
| Long session | Sesión activa > N horas (configurable) | WARNING |
| High message rate | > N mensajes/minuto en un perfil | WARNING |
| Service down | systemd service no está active | CRITICAL |
| Proxy error rate | > N% de requests con error en ventana de 5 min | WARNING |

No hay Prometheus ni Alertmanager. Es Python puro evaluando condiciones → mensaje a Telegram.

---

## 5. Estrategia de Adopción Atómica y Rollback

### Principio: cada cambio es una operación atómica con rollback inmediato.

#### Activación de proxy en un perfil

```
1. Leer config actual del perfil
2. Guardar copia completa en controlplane.db (config_backups)
3. Escribir nuevo base_url apuntando al proxy
4. Reiniciar service del perfil
5. Verificar que el service arrancó correctamente
6. Si falla verificación → restaurar backup → reiniciar → alertar
```

#### Desactivación de proxy (rollback)

```
1. Leer backup más reciente de config_backups
2. Restaurar config original
3. Reiniciar service del perfil
4. Verificar que el service arrancó correctamente
```

#### Reglas de rollback

- Todo rollback es ejecutable con un solo comando de Telegram: `/rollback {profile}`.
- El control plane mantiene los últimos 10 backups por perfil.
- Si el control plane se cae, Hermes sigue funcionando (con o sin proxy, según último estado de config).
- Si el proxy se cae pero el perfil apunta a él, Hermes recibe errores de conexión. Mitigación: health check del proxy que auto-restaura config original si detecta que el proxy no responde por > 60 segundos.

---

## 6. Fases de Implementación

### Fase 0 — Scaffolding (fundaciones)

**Entregable**: proyecto corriendo en Docker, sin funcionalidad visible aún.

- Estructura del repo Python (pyproject.toml, src layout)
- Docker Compose con single container, montando `~/.hermes` como volumen read-only
- `controlplane.db` schema inicial (migrations con alembic o manual)
- FastAPI app skeleton con health check endpoint
- Configuración centralizada (pydantic-settings, YAML o env vars)
- Tests unitarios del schema y config loader
- CI básico (lint + tests)

**Criterio de salida**: `docker compose up` levanta el container, `/health` responde 200, `controlplane.db` se crea con schema correcto.

### Fase 1 — Observer (read-only, cero impacto en Hermes)

**Entregable**: visibilidad completa del estado de Hermes via Telegram y dashboard.

- Reader de `state.db` en modo read-only (aiosqlite con `?mode=ro`)
- Monitor de systemd services (estado, uptime, restarts)
- Reader de configs de perfiles
- API REST: `GET /profiles`, `GET /profiles/{name}/status`, `GET /profiles/{name}/sessions`
- Bot Telegram: `/status`, `/status {profile}`, `/sessions {profile}`
- Dashboard HTMX: tabla de perfiles con estado, sesiones activas, último mensaje
- Alerta: service down → Telegram

**Criterio de salida**: con Hermes corriendo normalmente, el control plane muestra estado correcto de todos los perfiles via Telegram y dashboard. Hermes no sabe que existe.

### Fase 2 — Proxy + Costos + Budgets (opt-in per profile)

**Entregable**: proxy funcional con cost tracking y killswitch.

- Reverse proxy async (httpx) para OpenRouter
- Extracción de costos del campo `usage` en responses
- Tablas `cost_events` y `budgets` en `controlplane.db`
- Activación/desactivación de proxy por perfil con backup atómico de config
- Killswitch automático al exceder budget
- Bot Telegram: `/proxy enable {profile}`, `/proxy disable {profile}`, `/costs {profile}`, `/budget set {profile} {amount}`, `/rollback {profile}`
- Dashboard: sección de costos por perfil (diario, mensual), estado del proxy
- Alertas: budget warning (80%), budget exceeded (100%), proxy error rate
- Health check del proxy con auto-rollback si el proxy no responde

**Criterio de salida**: activar proxy en un perfil de test, enviar requests, ver costos registrados, simular exceso de budget y verificar killswitch, ejecutar rollback completo.

### v1 — Anomaly Flags + Hardening

**Entregable**: detección de anomalías simples y estabilidad para operación continua.

- Flags de anomalía basados en thresholds (NO machine learning, NO análisis semántico):
  - Sesión excesivamente larga (> N horas)
  - Rate de mensajes anormalmente alto (> N/min)
  - Gasto acumulado inusual (> N× promedio diario)
- Alertas de anomalía → Telegram con contexto (perfil, métrica, valor actual vs threshold)
- Dashboard: timeline de alertas, indicadores de anomalía por perfil
- Bot Telegram: `/alerts`, `/alerts {profile}`, `/thresholds`
- Graceful shutdown del proxy (drain connections antes de apagar)
- Retry logic en el proxy (con backoff, max 2 retries)
- Logs estructurados (JSON) para todo el control plane
- Documentación de operación

**Criterio de salida**: anomalías simuladas disparan alertas correctas. El sistema opera estable por 72 horas con proxy activo en al menos un perfil.

### Post-v1 (backlog priorizado, fuera del MVP)

- **v0.4**: Scheduler de perfiles (APScheduler embebido) — arrancar/parar perfiles por horario
- **v0.5**: Replay de sesiones (leer mensajes de state.db y re-renderizar)
- **v0.6**: Loop detection inteligente (heurísticas sobre patrones de mensajes repetidos)
- **Futuro**: Tailscale para acceso remoto al dashboard, multi-host

---

## 7. Riesgos y Mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Proxy introduce latencia perceptible en requests a OpenRouter | Media | Alto | Benchmark en fase 2. httpx async debe agregar < 50ms. Si excede, optimizar o ofrecer bypass. |
| R2 | Lectura concurrente de state.db causa lock contention con Hermes | Baja | Alto | Abrir con `?mode=ro` y `PRAGMA query_only=ON`. WAL mode en SQLite permite lectores concurrentes sin bloquear escritores. |
| R3 | Control plane se cae y perfil queda apuntando al proxy muerto | Media | Alto | Health check periódico (cada 30s). Si proxy no responde por > 60s, proceso watchdog restaura config original automáticamente. Docker restart policy `unless-stopped`. |
| R4 | Backup de config se corrompe o se pierde | Baja | Alto | Backups en `controlplane.db` (no en filesystem). Mantener últimos 10 por perfil. Validar backup antes de rollback. |
| R5 | Bot Telegram rate-limited por demasiadas alertas | Media | Bajo | Debounce de alertas: misma alerta no se repite en < 5 minutos. Agrupación de alertas si hay > 3 pendientes. |
| R6 | Costos reportados no coinciden con billing real de OpenRouter | Media | Medio | Reconciliación manual mensual contra dashboard de OpenRouter. Disclaimer en UI de que los costos son estimados. |
| R7 | Docker container consume más de 512 MB | Baja | Bajo | Memory limit en docker-compose. Monitor con `docker stats`. Alertar si > 80%. |

---

## 8. Criterios de Aceptación

### Fase 0
- [ ] `docker compose up` levanta el container sin errores
- [ ] `/health` responde `200 OK`
- [ ] `controlplane.db` se crea con schema correcto
- [ ] Tests pasan en CI

### Fase 1
- [ ] `/status` en Telegram muestra todos los perfiles con estado correcto
- [ ] Dashboard muestra tabla de perfiles actualizada
- [ ] Alerta de service down llega a Telegram en < 2 minutos
- [ ] state.db abierta en modo read-only verificable (no locks)
- [ ] Hermes no muestra cambios de comportamiento ni logs adicionales

### Fase 2
- [ ] Proxy activado en perfil de test intercepta requests correctamente
- [ ] Costos registrados en `controlplane.db` con desglose por modelo y perfil
- [ ] Killswitch detiene requests al exceder budget configurado
- [ ] Rollback restaura config original y reinicia service en < 10 segundos
- [ ] Health check auto-restaura config si proxy está caído > 60 segundos

### v1
- [ ] Flags de anomalía se disparan correctamente ante thresholds excedidos
- [ ] Alertas de anomalía llegan a Telegram con contexto útil
- [ ] Sistema opera estable 72 horas con proxy activo
- [ ] Logs estructurados en JSON disponibles via `docker logs`
- [ ] Latencia del proxy < 50ms sobre baseline de request directo a OpenRouter

---

## 9. Decisiones Cerradas

| Decisión | Resolución | Motivo |
|---|---|---|
| LiteLLM | **Descartado** | Demasiado pesado para single user, resuelve un problema que no tenemos |
| Framework web | **FastAPI** | Async nativo, ecosistema Python, sin build step |
| Dashboard | **HTMX + Jinja2** | Sin Node, sin build step, servido por FastAPI |
| Storage propio | **SQLite (controlplane.db)** | Simple, sin servidor, suficiente para single host |
| Acceso a state.db | **Read-only siempre** | Principio innegociable — no tocar datos de Hermes |
| Proxy HTTP | **httpx async** | Async nativo, lightweight, API moderna |
| Bot Telegram | **python-telegram-bot + long-polling** | Sin webhook (Tailscale no activo), biblioteca madura |
| Empaquetado | **Docker Compose, single container** | Hermes sigue como systemd service |
| Costos | **Solo OpenRouter** | Único provider usado actualmente |
| Loop detection | **Fuera del MVP** | Complejidad alta, valor incremental. Anomaly flags simples sí. |
| Scheduler | **Post-MVP (v0.4+)** | APScheduler embebido cuando se necesite |
| Lenguaje | **Python 3.12+** | Python-first por decisión del usuario |
| RAM | **512 MB máximo** | Constraint de diseño para single container |
| Repo | **Separado (hermes-controlplane)** | Aislamiento total del código de Hermes |
| Pause semántica | **Proxy retorna 503** | Soft-stop sin matar el proceso de Hermes |
| Kill semántica | **systemctl --user stop** | Hard-stop del proceso |

---

## 10. Decisiones Abiertas Mínimas

| Decisión | Opciones | Cuándo resolver | Impacto si se posterga |
|---|---|---|---|
| Puerto del proxy y API REST | 8100-8199 range | Fase 0 | Ninguno — se elige un puerto libre |
| Estructura de comandos Telegram | Flat (`/status`, `/costs`) vs subcomandos (`/hermes status`) | Fase 1 | Bajo — refactorizable |
| Formato de config del control plane | YAML vs env vars vs ambos | Fase 0 | Bajo — pydantic-settings soporta ambos |
| Autenticación del bot Telegram | Token directo vs restricción por chat_id | Fase 1 | Medio — sin restricción cualquiera con el token puede operar |
| Precios de modelos OpenRouter | Hardcoded vs fetch de API de OpenRouter | Fase 2 | Medio — hardcoded se desactualiza, API agrega dependencia |
| Estrategia de migrations de controlplane.db | Alembic vs SQL manual versionado | Fase 0 | Bajo — pocas tablas en MVP |
