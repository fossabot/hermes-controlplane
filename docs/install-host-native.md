# Host-native install

This is the official installation path for v0.1 on Linux.

It keeps the app simple:
- install dependencies with `uv`
- run on the host
- manage it with `systemd --user`
- bind to `127.0.0.1`

## Platform support

Official service-install support:
- Linux with `systemd --user`

Manual local development support:
- Linux
- macOS

Notes:
- `install.sh` installs and uninstalls a user service on Linux only
- macOS can run the app manually with `uv run uvicorn ...`, but there is no official launchd installer in v0.1

## Requirements

- Python 3.11+
- `uv`
- `systemd --user`
- Hermes already installed on the host
- access to the Hermes home directory

## 1. Clone and configure

```bash
git clone <your-fork-or-local-copy>
cd hermes-controlplane
cp .env.example .env
```

Edit `.env` if needed.

Example values:

```env
HERMES_HOME=${HOME}/.hermes
CONTROLPLANE_HOST=127.0.0.1
CONTROLPLANE_PORT=8780
CONTROLPLANE_LOG_LEVEL=info
```

## 2. Install dependencies

```bash
uv sync
```

## 3. Run once manually

```bash
uv run uvicorn hermes_controlplane.main:app --host 127.0.0.1 --port 8780
```

Open:
- `http://127.0.0.1:8780`

## 4. Install as a user service

Use the example unit at:
- `contrib/systemd/hermes-controlplane.service.example`

You can also use:

```bash
./install.sh install
```

That script renders and installs a user service automatically.

## 4b. Uninstall the user service

```bash
./install.sh uninstall
```

This removes the `systemd --user` service unit and stops the service.
It does not delete the repository, `.env`, or `.venv`.

## 5. Remote access with SSH tunnel

Recommended:

```bash
ssh -L 8780:127.0.0.1:8780 your-user@your-server
```

Then open:
- `http://127.0.0.1:8780`

## 6. Advanced option: Tailscale

If the host is already on a trusted tailnet, Tailscale can be a good remote-access layer.

Even in that setup, keep the app localhost-first unless you have a clear reason to change the bind address.

## Not the official path

Docker is not the official deployment path for v0.1.
