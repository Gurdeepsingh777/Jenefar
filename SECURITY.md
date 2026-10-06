# Security

Jenefar defaults to localhost binding, blocks private/loopback URLs at the research tool boundary, redacts common credentials in audit records, uses expiring HMAC approval tokens, and persists runtime state with bounded history.

Before exposing Jenefar beyond localhost:
- set a strong JENEFAR_APPROVAL_SECRET;
- run the production security workflow;
- review tool permissions and workspace roots;
- keep data and backups filesystem-restricted;
- put the service behind authenticated TLS if remote access is required.


## Local production setup

Run `.venv/bin/python scripts/configure_production.py --no-provider` once to generate and persist a random approval secret in `.env` with restrictive permissions. Never commit `.env`.

Online providers are optional when Ollama is healthy. If an online provider is desired for failover, configure its API key with the same script; the key is entered through a hidden prompt and is never printed.

## Remote access

Jenefar binds to localhost by default. A non-loopback bind requires Basic Auth and TLS certificate/key configuration. The server uses TLS 1.2+ when configured. Do not set `JENEFAR_ALLOW_INSECURE_REMOTE=1` unless a trusted external TLS/authentication proxy is already protecting the service.

Python's built-in `http.server` is suitable for this bounded local application surface but is not a general internet-facing production web server; for public deployment, a hardened reverse proxy should terminate TLS and enforce additional authentication/rate limiting. citeturn2search0turn2search1

## Real-machine E2E

Use `scripts/live_e2e.py` for physical microphone/STT/TTS, native screen vision/grounding, real Chromium automation, VRM browser validation, and long-running task execution. These checks are opt-in and never report hardware as passed without exercising it.
