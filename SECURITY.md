# Security

## Supported version

Current public target:
- v0.1.x

## Deployment posture

Hermes Control Plane is designed to run locally on the same host as Hermes.

Recommended defaults:
- bind FastAPI to `127.0.0.1`
- run as a `systemd --user` service
- access it locally or through SSH tunneling

Recommended remote access:

```bash
ssh -L 8780:127.0.0.1:8780 your-user@your-server
```

Advanced option:
- Tailscale on a trusted tailnet can work well when you need remote access
- direct public internet exposure is not recommended for v0.1

## Authentication

There is no custom in-app authentication layer in v0.1.

That is intentional. The security boundary is the host and network path:
- localhost binding
- SSH tunnel for remote access
- optional private-network tooling such as Tailscale

## Data handling

The app reads Hermes state databases in SQLite read-only mode.

Sensitive operational data may still appear in Hermes state or cron output, so you should:
- restrict host access appropriately
- avoid exposing the service directly to the internet
- review cron output retention and sharing practices

## Reporting a vulnerability

Please report security issues privately to the maintainers before opening a public issue.

When reporting, include:
- affected version
- reproduction steps
- impact assessment
- any suggested mitigation
