# Oxion AI provider setup for Jenefar

Jenefar's LLM provider pool supports Oxion AI through its OpenAI-compatible Chat Completions API.

## 1. Configure the API key

Copy .env.example to .env if you have not already done so. Keep all values containing spaces in quotes (especially JENEFAR_WAKE_PHRASES and JENEFAR_BROWSER_TTS_INSTRUCTIONS). Do not run source .env until those values are quoted; dotenv loads .env automatically when Jenefar starts. In your local .env, set:

    OXION_API_KEY=cc_your_actual_key_here
    OXION_MODEL=claude-sonnet-5
    JENEFAR_PROVIDER_ORDER=oxion,openai,openrouter,gemini,groq,cerebras
    JENEFAR_ADAPTIVE_ROUTING=0

Replace the example value with the key copied from Oxion AI Dashboard → API Keys. Do not commit .env, paste the key into chat, or place it in browser-side code. If the key was exposed, revoke it and create a new one.

## 2. Endpoint and model

Jenefar uses https://www.oxionai.com/v1 as the base URL. OXION_MODEL must exactly match a model ID available to your Oxion account. The default is claude-sonnet-5 based on the model shown in the account screenshot; if Oxion's GET /v1/models returns a different ID, use that exact ID instead.

To use a different model for one task role, set e.g. JENEFAR_OXION_MODEL_CODING=qwen3.8-27b or JENEFAR_OXION_MODEL_REASONING=deepseek-v4-pro-0813. Confirm model IDs and capabilities against Oxion's live model list first.

## 3. Test the API key independently

From the Jenefar repository root, run:

    set -a; source .env; set +a
    curl -fsS https://www.oxionai.com/v1/models -H "Authorization: Bearer $OXION_API_KEY"

Do not print or share the key. A successful request should return the model list.

Then run the UI with online-only mode if you want to prevent silent Ollama fallback:

    python run.py --voice-auto --online-only

The provider pool tries Oxion first when its key is configured and falls through to other configured online providers after provider errors. With --online-only, if all online providers fail, Jenefar reports the failure instead of switching to Ollama. Omit --online-only when you want offline fallback.

## Notes

- Oxion supports an OpenAI-compatible API, so Jenefar's existing OpenAI SDK client and Chat Completions/tool-calling path are reused.
- This provider addition does not route browser Realtime voice, STT, or TTS through Oxion; those are separate integrations.
- Do not assume a model supports tools or vision just because it is listed. Check its advertised capabilities before relying on autonomous tool calls or image input.
- No live API test can be completed until you configure your private key locally.
