# Free Claude Code gateway integration

Jenefar can optionally route model requests through a separately installed Free Claude Code (FCC) server. FCC is not installed as a Jenefar Python dependency: its current project metadata requires exactly Python 3.14.10, while Jenefar CI supports Python 3.10–3.13.

## Start FCC separately

Install and configure FCC using its upstream instructions:
https://github.com/Alishahryar1/free-claude-code

On Linux, start its server with `fcc-server`. FCC's documented default port is 8082. Configure at least one provider and a model in FCC's Admin UI before sending requests.

## Enable FCC in Jenefar

Add the following to Jenefar's `.env`:

```dotenv
FCC_ENABLED=true
FCC_BASE_URL=http://127.0.0.1:8082/v1
FCC_API_KEY=
FCC_MODEL=your-provider/your-model
JENEFAR_PROVIDER_ORDER=fcc,openrouter,gemini,groq
```

Replace `your-provider/your-model` with a model identifier actually configured in FCC. If FCC Proxy Authentication is enabled, set `FCC_API_KEY` to the same secret configured in FCC. Keep FCC bound to localhost unless remote access is intentional and protected by authentication and network controls.

FCC is opt-in. When `FCC_ENABLED` is false, the provider is not eligible for routing. When enabled, Jenefar uses its existing OpenAI Responses client against FCC's `/v1/responses` endpoint. Provider errors flow through Jenefar's existing cooldown/failover path, followed by its existing local-model fallback.

The health helper checks FCC's unauthenticated `/health` endpoint; it is intended for diagnostics and does not make provider configuration depend on a network request.

## Security and limitations

- Keep API keys and proxy tokens in the local `.env`; never commit secrets.
- FCC and Jenefar remain separate processes and dependency environments.
- Free-tier quota, model availability, and provider terms are controlled by upstream providers and can change.
- FCC is AGPL-3.0-only. Review its license obligations before redistributing a combined product or modifying/distributing FCC itself.
- Jenefar's tool broker, approval flow, authorization scopes, and audit boundary remain in Jenefar. FCC must not be treated as an authorization layer for local actions.
