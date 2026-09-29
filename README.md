# Jenefar AI

Jenefar is a modular, voice-first multi-agent AI assistant designed to grow into a desktop automation, coding, cybersecurity, research, robotics, and authorized tool-execution platform.

## Current release

The core now includes:

- Master orchestrator + deterministic planner + specialist router
- Model-backed Python, repository, cybersecurity, bug-bounty, robotics, and research agents
- OpenAI Responses API adapter
- Optional hosted web search for the research agent
- Short-term session memory passed to specialists
- Centralized tool broker with approval-gated function calls
- Explicit permission boundary for terminal execution
- Authorization-scope and JSONL audit logging
- Safe discovery of common Kali/Linux security tools
- "Hi Jenefar" / "Hello Jenefar" activation logic
- Text runtime for immediate testing
- Bounded and continuous microphone -> STT -> orchestrator -> TTS runtimes
- Local particle avatar with optional Three.js/VRM rendering and expressions
- Browser Realtime speech-to-speech transport using ephemeral client secrets
- Persistent SQLite memory + FTS5 retrieval
- URL and public GitHub research ingestion
- Read-only URL/GitHub research tools for the model
- GitHub repository architecture analysis and change planning
- PDF/DOCX/text document extraction and RAG ingestion

The LLM and voice integrations remain isolated behind adapters so providers can be changed later.

## Quick start

```bash
git clone https://github.com/Gurdeepsingh777/Jenefar.git
cd Jenefar

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# Put your OpenAI API key in .env
python run.py
```

Then type:

```text
Hi Jenefar
```

and ask a question. Without an API key, the runtime reports that the model provider is not configured.

## Voice mode

Bounded voice mode:

```bash
python run.py --voice
```

Continuous voice mode:

```bash
python run.py --voice-continuous
```

Continuous mode keeps the microphone open, uses local energy-based VAD to segment utterances, sends only detected utterances to STT, applies the same wake-word gate and orchestrator routing, then streams TTS back to the speakers. Tune the VAD with the `JENEFAR_VOICE_*` environment variables in `.env`.

## Avatar and realtime voice

Launch the avatar UI:

```bash
python run.py --avatar
```

Run continuous local VAD/STT/TTS with the avatar:

```bash
python run.py --avatar --voice-continuous
```

Native desktop shell:

```bash
python run.py --desktop
```

Direct realtime mode:

```bash
python run.py --realtime
```

For the 3D path, put a licensed VRM model at a local path and set:

```env
JENEFAR_AVATAR_VRM_PATH=data/avatar.vrm
```

The browser loads the VRM with Three.js + `@pixiv/three-vrm` when the file is present and falls back to the procedural avatar when it is not. Runtime events drive expressions and mouth animation.

For low-latency browser speech-to-speech, start `--avatar` and press **START REALTIME**. The server mints a short-lived Realtime client secret; the browser then establishes the WebRTC media session directly with OpenAI. The server never sends the long-lived API key to the browser.

## Production desktop shell and settings

The local avatar server exposes non-secret UI settings and an evaluation dashboard. The optional `pywebview` shell wraps the same UI in a native desktop window. The settings store allowlists only UI preferences; API keys are never written to it.

## Native wake word

Install optional runtime integrations:

```bash
pip install -r requirements-optional.txt
```

Configure a custom openWakeWord model:

```env
JENEFAR_WAKEWORD_MODEL_PATH=/path/to/your/jenefar_wakeword.tflite
JENEFAR_WAKEWORD_THRESHOLD=0.55
```

With a model configured, continuous voice detection performs local wake-word inference before sending an utterance to STT. Without a configured model, Jenefar keeps its transcript-based wake-word fallback.

Prepare a reproducible custom wake-word training config:

```bash
python run.py --wakeword-prepare "Hi Jenefar"
python run.py --wakeword-train all --wakeword-config data/wakeword/jenefar.yaml
```

The trainer wraps the upstream openWakeWord training entry point. Training still requires the local Piper sample generator, room-impulse responses, background clips and feature datasets; the upstream example documents those configuration inputs and its large-sample training workflow. citeturn100035search0turn100035search1

## Desktop automation and robotics

Desktop primitives and robotics serial commands are approval-gated. Configure robotics hardware with:

```env
JENEFAR_ROBOT_SERIAL_PORT=/dev/ttyUSB0
JENEFAR_ROBOT_BAUDRATE=115200
```

Jenefar exposes read-only screen/serial discovery plus confirmed click, typing, keyboard, screenshot and bounded robot commands.

Optional robotics adapters are also available for MQTT and ROS2. They are loaded only when invoked.

## Security execution profiles

Authorized security execution is still deny-by-default. The constrained profiles now include `nmap`, `whatweb` and `nikto`; each target must pass `authorized_targets` and each execution requires confirmation.

## Knowledge graph and evaluation

Search learned relations:

```bash
python run.py --graph-search Jenefar
```

View recent runtime evaluation signals:

```bash
python run.py --evaluation-report
python run.py --evaluation-dashboard
```

The evaluation loop records quality signals but does not autonomously rewrite code or weaken security policy.

## External research and RAG

Index a public URL:

```bash
python run.py --index-url "https://example.com/docs"
```

Index a public GitHub repository:

```bash
python run.py --index-github "owner/repository" --github-ref main --github-max-files 20
```

Restrict GitHub indexing to a path:

```bash
python run.py --index-github "owner/repository" --github-path docs --github-path README.md
```

Search the accumulated knowledge:

```bash
python run.py --memory-search "authentication architecture"
```

GitHub ingestion uses the public REST contents/tree APIs and only reads supported text/code files; it never writes to the remote repository or executes downloaded code. citeturn973821search0turn973821search1

## Research/web search

The research agent can enable the Responses API hosted `web_search` tool for current/source-sensitive queries. OpenAI documents `web_search` as the current Responses API web-search mechanism for new integrations.

## Repository analysis

Summarize a public repository without executing its code:

```bash
python run.py --analyze-github "owner/repository" --github-ref main
```

Create a read-only change plan:

```bash
python run.py --plan-github "owner/repository" --plan-task "add authentication tests"
```

The repository engineering agent can perform the same analysis through the internal tool broker. It does not write to or execute code from remote repositories.

## Document ingestion

PDF:

```bash
python run.py --index-document ./docs/manual.pdf
```

DOCX:

```bash
python run.py --index-document ./docs/specification.docx
```

The extracted text enters the same SQLite/FTS5 memory index used by conversation and web/GitHub research.

## Project layout

```text
jenefar/
├── core/          config, session, planner, routing, LLM
├── voice/         wake word, bounded/continuous voice runtimes
├── avatar/        live state bridge, expressions, particle UI
├── agents/        specialist agents
├── tools/         registry, terminal gate, Kali discovery
├── execution/     execution policy boundaries
├── memory/        SQLite/FTS5 persistent memory
├── research/      URL/GitHub ingestion and fetching
└── critic/        result verification

tests/              automated tests
```

## Authorized security scope

Security testing is deny-by-default until you configure authorized targets in `config.yaml`:

```yaml
security:
  authorized_targets:
    - "lab.example.com"
    - "192.168.1.0/24"
```

Scope checks accept exact host/IP values and IP CIDRs. Every tool approval, execution, error, and scope check is written to the configured JSONL audit log.

## Safety boundary

Jenefar's security tooling is intended for systems and targets you are authorized to test. Privileged, network-impacting, or otherwise high-impact actions remain behind explicit confirmation and policy controls. Tool discovery does not execute discovered tools.

## Roadmap

Completed in the current runtime:
- Specialist multi-agent routing and planner
- Approval-aware function-calling tool broker
- Persistent SQLite/FTS5 memory plus knowledge graph
- URL/GitHub/document research ingestion
- Authorized security scope, audit logging and constrained nmap/WhatWeb/Nikto profiles
- Continuous local VAD/STT/TTS voice runtime
- Optional local openWakeWord integration
- Particle avatar with runtime expressions and speech-reactive animation
- Three.js/VRM renderer with phoneme-driven mouth animation
- Browser WebRTC Realtime speech-to-speech transport
- Approval-gated desktop automation primitives
- Approval-gated serial robotics primitives
- Runtime evaluation and quality-signal logging

Next major milestones:
1. Native custom wake-word training/packaging for the exact “Hi Jenefar” phrase
2. Full action-tool approval UX inside the Realtime data channel
3. Production desktop app shell and persistent settings UI
4. Expanded robotics adapters (MQTT/ROS2) and device telemetry
5. Stronger semantic/embedding-backed knowledge graph retrieval
6. Automated evaluation suites and regression dashboards
