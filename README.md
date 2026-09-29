# Jenefar AI

Jenefar is a modular, voice-first multi-agent AI assistant designed to grow into a desktop automation, coding, cybersecurity, research, robotics, and authorized tool-execution platform.

## Current release

The core now includes:

- Master orchestrator + deterministic planner + specialist router
- Model-backed Python, cybersecurity, bug-bounty, robotics, and research agents
- OpenAI Responses API adapter
- Optional hosted web search for the research agent
- Short-term session memory passed to specialists
- Centralized tool broker with approval-gated function calls
- Explicit permission boundary for terminal execution
- Authorization-scope and JSONL audit logging
- Safe discovery of common Kali/Linux security tools
- "Hi Jenefar" / "Hello Jenefar" activation logic
- Text runtime for immediate testing
- Optional microphone -> OpenAI transcription -> agent -> OpenAI TTS runtime
- Persistent SQLite memory + FTS5 retrieval
- URL and public GitHub research ingestion
- Read-only URL/GitHub research tools for the model

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

The OpenAI Python SDK provides microphone and local audio helpers as an optional voice extra.

Install the optional helper dependencies:

```bash
pip install "openai[voice_helpers]"
python run.py --voice
```

Voice mode records a bounded turn, transcribes it, applies the same wake-word and routing flow, then speaks the response.

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

## Project layout

```text
jenefar/
├── core/          config, session, planner, routing, LLM
├── voice/         wake word, voice adapters, OpenAI voice runtime
├── agents/        specialist agents
├── tools/         registry, terminal gate, Kali discovery
├── execution/     execution policy boundaries
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

1. Native continuous wake-word detection
2. Realtime speech-to-speech mode
3. Function-calling tool router
4. Sandboxed/authorized Kali tool execution with scope controls
5. Desktop automation
6. Desktop automation
7. Long-term memory and knowledge graph
8. Robotics integrations
9. Evaluation and self-improvement loops
