# Jenefar AI

Jenefar is a modular, voice-first multi-agent AI assistant designed to grow into a desktop automation, coding, cybersecurity, research, robotics, and authorized tool-execution platform.

## Current release

The core now includes:

- Master orchestrator + deterministic planner + specialist router
- Model-backed Python, cybersecurity, bug-bounty, robotics, and research agents
- OpenAI Responses API adapter
- Optional hosted web search for the research agent
- Short-term session memory passed to specialists
- Explicit permission boundary for terminal execution
- Safe discovery of common Kali/Linux security tools
- "Hi Jenefar" / "Hello Jenefar" activation logic
- Text runtime for immediate testing
- Optional microphone -> OpenAI transcription -> agent -> OpenAI TTS runtime

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

The OpenAI Python SDK provides microphone and local audio helpers as an optional voice extra. citeturn657415search0turn657415search2

Install the optional helper dependencies:

```bash
pip install "openai[voice_helpers]"
python run.py --voice
```

Voice mode records a bounded turn, transcribes it, applies the same wake-word and routing flow, then speaks the response.

## Research/web search

The research agent can enable the Responses API hosted `web_search` tool for current/source-sensitive queries. OpenAI documents `web_search` as the current Responses API web-search mechanism for new integrations. citeturn325453search5

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

## Safety boundary

Jenefar's security tooling is intended for systems and targets you are authorized to test. Privileged, network-impacting, or otherwise high-impact actions remain behind explicit confirmation and policy controls. Tool discovery does not execute discovered tools.

## Roadmap

1. Native continuous wake-word detection
2. Realtime speech-to-speech mode
3. Function-calling tool router
4. Sandboxed/authorized Kali tool execution with scope controls
5. GitHub/document/RAG connectors
6. Desktop automation
7. Long-term memory and knowledge graph
8. Robotics integrations
9. Evaluation and self-improvement loops
