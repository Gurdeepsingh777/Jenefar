# Jenefar AI

Jenefar is a modular, voice-first multi-agent AI assistant designed to grow into a desktop automation, coding, cybersecurity, research, robotics, and tool-execution platform.

## Current release

This repository contains the first working Jenefar core:

- Master orchestrator and agent router
- Coding, cybersecurity, bug-bounty, robotics, and research agents
- Dynamic tool registry
- Explicit permission boundary for command execution
- Short-term memory abstraction
- Critic/verifier layer
- "Hi Jenefar" / "Hello Jenefar" activation logic
- Text-mode runtime for immediate testing

The voice layer is isolated so a real microphone/STT/TTS backend can be added without rewriting the agent architecture.

## Quick start

```bash
git clone https://github.com/Gurdeepsingh777/Jenefar.git
cd Jenefar

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
python run.py
```

Then type:

``	ext
Hi Jenefar
```

and Jenefar will wake. In the current single-turn mode, the response returns her to sleep after each command.

## Project layout

``	ext
jenefar/
├── core/          orchestration, routing, state, configuration
├── voice/         wake-word, microphone, STT, TTS interfaces
├── agents/        specialist agents
├── tools/         tool registry and execution tools
├── memory/        memory abstractions
├── execution/     permission and audit boundaries
└── critic/        result verification

scripts/            setup helpers
tests/              automated tests
data/               runtime data
```

## Safety boundary

Jenefar's security tooling is intended for systems and targets you are authorized to test. Privileged, network-impacting, or otherwise high-impact actions should pass an explicit approval and policy layer before execution.

## Roadmap

1. Real microphone + wake-word backend
2. STT/TTS
3. Model-backed Master Agent
4. Web/GitHub/document research and RAG
5. Kali/Linux tool discovery and sandboxed execution
6. Desktop automation
7. Long-term memory and knowledge graph
8. Robotics integrations
9. Evaluation/self-improvement loops
