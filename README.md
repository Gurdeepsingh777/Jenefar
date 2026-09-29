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
- Bounded and continuous microphone -> STT -> orchestrator -> TTS runtimes\n- Local real-time AI avatar UI with state-driven particle animation
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

## Avatar mode

Launch Jenefar with the local particle avatar:

```bash
python run.py --avatar --voice-continuous
```

The browser UI receives real-time `listening`, `thinking`, `speaking`, `waiting_approval` and `idle` events from the Python runtime. The avatar uses a procedural particle field and expressive motion layer, so it works without a dedicated GPU avatar model. The state bridge is intentionally isolated so a future model-backed renderer can replace the procedural layer without changing the orchestrator.

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

Completed foundations:
- Specialist multi-agent routing and planner
- Function-calling tool broker with explicit approvals
- Persistent SQLite/FTS5 memory and document/web/GitHub ingestion
- Authorized security scope and audit logging
- Continuous microphone VAD -> STT -> orchestrator -> TTS
- Live particle avatar with runtime states, speech-reactive animation and expressions

Next major milestones:
1. Native low-latency wake-word engine
2. Realtime speech-to-speech transport
3. Full 3D/VRM avatar with neural/phoneme-aware lip-sync
4. Desktop automation with approval/audit boundaries
5. Broader sandboxed authorized security-tool profiles
6. Robotics device integrations
7. Evaluation/self-improvement and richer knowledge-graph memory
