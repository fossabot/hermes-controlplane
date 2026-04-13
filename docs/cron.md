# Cron operations

Cron is part of the supported v0.1 feature set.

## What the app does

The dashboard can:
- list global cron jobs
- list profile-scoped cron jobs
- show cron output history
- trigger run, pause, and resume actions

## How actions work

Cron actions are delegated to the Hermes CLI.

That means the control plane does not invent a second cron engine. It operates against Hermes' existing cron behavior.

## Global vs profile-scoped

Global routes read from:
- `~/.hermes/cron/`

Profile routes read from:
- `~/.hermes/profiles/<name>/cron/`

## Output handling

Cron outputs are read from Hermes output directories and displayed in the UI.

Treat cron output as operational data that may contain sensitive information.

## Operational guidance

- keep the service bound to localhost
- use SSH tunnel for remote access
- review who can access the host user account
- avoid sharing cron output without checking its contents
