# Jenefar AI

Jenefar ek modular, voice-first multi-agent AI assistant hai jo dheere-dheere ek powerful desktop automation, coding, cybersecurity, research, robotics aur authorized tool-execution platform ke roop me grow karne ke liye design kiya gaya hai.

## Current release

Abhi Jenefar ke core me ye features available hain:

- Master orchestrator + deterministic planner + specialist router
- Python, repository, cybersecurity, bug-bounty, robotics aur research ke liye model-backed specialist agents
- OpenAI Responses API adapter
- Research agent ke liye optional hosted web search
- Short-term session memory jo specialist agents ko pass hoti hai
- Centralized tool broker with approval-gated function calls
- Terminal execution ke liye explicit permission boundary
- Authorization scope aur JSONL audit logging
- Common Kali/Linux security tools ki safe discovery
- "Hi Jenefar" / "Hello Jenefar" activation logic
- Immediate testing ke liye text runtime
- Bounded aur continuous microphone -> STT -> orchestrator -> TTS runtimes
- Local particle avatar with optional Three.js/VRM rendering aur expressions
- Ephemeral client secrets ke through browser Realtime speech-to-speech transport
- Persistent SQLite memory + FTS5 retrieval
- URL aur public GitHub research ingestion
- Model ke liye read-only URL/GitHub research tools
- GitHub repository architecture analysis aur change planning
- PDF/DOCX/text document extraction aur RAG ingestion
- "Hello Jenefar" se activate hone par Hinglish response preference
- Safe external asset provisioning for wake-word training aur sample VRM

LLM aur voice integrations adapters ke peeche isolated rakhe gaye hain, isliye future me providers ko replace karna easier rahega.

## Quick start

```bash
git clone https://github.com/Gurdeepsingh777/Jenefar.git
cd Jenefar

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# .env me apni OpenAI API key daalo
python run.py
```

Phir type karo:

```text
Hi Jenefar
```

aur apna question poochho. API key configured nahi hogi to runtime model provider configuration error batayega.

## Language behavior

Jenefar me wake phrase ke basis par response language preference set ki ja sakti hai.

Jab tum bolo:

```text
Hello Jenefar
```

to Jenefar Hinglish me reply karega.

Example:

```text
You > Hello Jenefar
Jenefar > Haan, boliye. Main sun rahi hoon.
```

Agar wake phrase ke saath command bhi ho:

```text
You > Hello Jenefar Python kya hota hai?
```

to request ko Hinglish response preference ke saath specialist agent tak bheja jayega.

Hinglish mode me:
- Hindi ko primarily Roman script me use kiya jayega.
- English technical terms natural form me rahenge.
- Code, commands, filenames, APIs aur syntax ko translate nahi kiya jayega.
- "Hi Jenefar" ke liye normal/default response language behavior use hota hai.
- Browser Realtime mode me bhi "Hello Jenefar" ke liye Hinglish instruction configured hai.

## Voice mode

Bounded voice mode:

```bash
python run.py --voice
```

Continuous voice mode:

```bash
python run.py --voice-continuous
```

Continuous mode microphone ko open rakhta hai, local energy-based VAD se utterances detect karta hai, detected utterances ko STT ke liye bhejta hai, wake-word gate apply karta hai, phir same orchestrator routing use karta hai aur TTS response speakers par play karta hai.

Voice VAD ko `.env` ke `JENEFAR_VOICE_*` variables se tune kiya ja sakta hai.

## Avatar aur realtime voice

Avatar UI launch karne ke liye:

```bash
python run.py --avatar
```

Avatar ke saath continuous local VAD/STT/TTS:

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

Repository me ek safe first-run asset provisioner bhi hai jo redistribution-documented sample avatar ko local machine par la sakta hai:

```bash
python run.py --setup-assets avatar
```

Ye pinned upstream source se `AvatarSample_A_1.0.vrm.glb` download karta hai, `data/avatar/AVATAR_LICENSE.txt` me provenance record karta hai aur avatar server us model ko automatically detect kar leta hai.

Apna khud ka licensed VRM use karna ho to:

```env
JENEFAR_AVATAR_VRM_PATH=/absolute/path/to/your/avatar.vrm
```

VRM available hone par browser Three.js + `@pixiv/three-vrm` ke through usse load karta hai. VRM available na ho to procedural avatar fallback use hota hai. Runtime events expressions aur mouth animation drive karte hain.

Low-latency browser speech-to-speech ke liye `--avatar` start karo aur **START REALTIME** press karo. Server short-lived Realtime client secret mint karta hai; browser uske baad WebRTC session directly OpenAI ke saath establish karta hai. Long-lived API key browser ko send nahi hoti.

## Production desktop shell aur settings

Local avatar server non-secret UI settings aur evaluation dashboard expose karta hai.

Optional `pywebview` shell same UI ko native desktop window ke andar wrap karta hai.

Settings store sirf allowlisted UI preferences rakhta hai. API keys is settings store me save nahi hoti.

## Native wake word

Optional runtime integrations install karo:

```bash
pip install -r requirements-optional.txt
```

Custom openWakeWord model configure karne ke liye:

```env
JENEFAR_WAKEWORD_MODEL_PATH=/path/to/your/jenefar_wakeword.tflite
JENEFAR_WAKEWORD_THRESHOLD=0.55
```

Model configured hone par continuous voice detection STT ko audio bhejne se pehle local wake-word inference karti hai.

Agar custom model configured nahi hai, Jenefar transcript-based wake-word fallback use karta hai.

### Real wake-word training resources

Actual training resources provision karne ke liye:

```bash
pip install -r requirements-optional.txt
python run.py --setup-assets wakeword
python run.py --wakeword-prepare "Hi Jenefar"
python run.py --wakeword-prepare-validation --wakeword-validation-hours 11.3
python run.py --wakeword-train all --wakeword-config data/wakeword/jenefar.yaml
```

Safe profile me Jenefar ye resources arrange karta hai:
- `dscripka/piper-sample-generator` aur uska LibriTTS generator model
- OpenSLR SLR26 simulated RIRs
- OpenSLR SLR12 LibriSpeech dev-clean/dev-other speech material

Agar larger room/noise pool chahiye to:

```bash
python run.py --setup-assets wakeword --wakeword-asset-profile rich
```

Rich profile me additional OpenSLR SLR28 RIR/noise resources bhi aate hain.

Jenefar default training config me public openWakeWord ACAV100M feature file ko mandatory dependency nahi banata.

Validation step:

```bash
python run.py --wakeword-prepare-validation --wakeword-validation-hours 11.3
```

ke through `data/wakeword/validation_set_features.npy` generate hota hai.

Ye file false-positive validation ke liye use hoti hai.

Important: actual `Hi Jenefar` neural model training local machine par hoti hai. Public repository me trained binary, huge datasets ya generated model files commit nahi kiye jate.

## Desktop automation aur robotics

Desktop primitives aur robotics serial commands approval-gated hain.

Serial robotics setup:

```env
JENEFAR_ROBOT_SERIAL_PORT=/dev/ttyUSB0
JENEFAR_ROBOT_BAUDRATE=115200
```

Jenefar read-only screen/serial discovery ke saath confirmed click, typing, keyboard, screenshot aur bounded robot commands expose karta hai.

Optional robotics adapters:
- MQTT
- ROS2

Ye adapters sirf invoke hone par load hote hain.

MQTT configuration:

```env
JENEFAR_MQTT_HOST=
JENEFAR_MQTT_PORT=1883
JENEFAR_MQTT_COMMAND_TOPIC=jenefar/robot/command
JENEFAR_MQTT_TELEMETRY_TOPIC=jenefar/robot/telemetry
```

## Security execution profiles

Authorized security execution abhi bhi deny-by-default hai.

Constrained profiles:
- `nmap`
- `whatweb`
- `nikto`

Har target ko configured `authorized_targets` scope pass karna hota hai aur har execution ke liye confirmation required hota hai.

## Knowledge graph aur evaluation

Learned relations search karne ke liye:

```bash
python run.py --graph-search Jenefar
```

Recent runtime evaluation signals dekhne ke liye:

```bash
python run.py --evaluation-report
python run.py --evaluation-dashboard
```

Evaluation loop quality signals record karta hai, lekin khud se code rewrite ya security policy weakening nahi karta.

## External research aur RAG

Public URL index karne ke liye:

```bash
python run.py --index-url "https://example.com/docs"
```

Public GitHub repository index karne ke liye:

```bash
python run.py --index-github "owner/repository" --github-ref main --github-max-files 20
```

GitHub indexing ko specific path tak restrict karna ho:

```bash
python run.py --index-github "owner/repository" --github-path docs --github-path README.md
```

Accumulated knowledge search:

```bash
python run.py --memory-search "authentication architecture"
```

GitHub ingestion public REST contents/tree APIs use karta hai aur sirf supported text/code files read karta hai. Ye remote repository me write nahi karta aur downloaded code execute nahi karta.

## Research / web search

Research agent current aur source-sensitive queries ke liye Responses API ka hosted `web_search` tool enable kar sakta hai.

## Repository analysis

Public repository ko execute kiye bina summarize karne ke liye:

```bash
python run.py --analyze-github "owner/repository" --github-ref main
```

Read-only change plan generate karne ke liye:

```bash
python run.py --plan-github "owner/repository" --plan-task "add authentication tests"
```

Repository engineering agent bhi same analysis internal tool broker ke through kar sakta hai.

Ye remote repository me code write nahi karta aur remote code execute nahi karta.

## Document ingestion

PDF:

```bash
python run.py --index-document ./docs/manual.pdf
```

DOCX:

```bash
python run.py --index-document ./docs/specification.docx
```

Extracted text same SQLite/FTS5 memory index me store hota hai jise conversation aur web/GitHub research bhi use karte hain.

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
├── research/      URL/GitHub ingestion aur fetching
├── assets/        pinned external asset provisioning aur provenance
└── critic/        result verification

tests/              automated tests
```

## Authorized security scope

Security testing deny-by-default hai jab tak tum `config.yaml` me authorized targets configure nahi karte:

```yaml
security:
  authorized_targets:
    - "lab.example.com"
    - "192.168.1.0/24"
```

Scope checks exact host/IP values aur IPv4/IPv6 CIDRs accept karte hain.

Har tool approval, execution, error aur scope check configured JSONL audit log me write hota hai.

## Safety boundary

Jenefar ki security tooling un systems aur targets ke liye intended hai jinke liye tum authorized ho.

Privileged, network-impacting ya otherwise high-impact actions explicit confirmation aur policy controls ke peeche rehte hain.

Tool discovery kisi discovered tool ko automatically execute nahi karti.

## Current status

Current runtime me ye major parts complete hain:

- Specialist multi-agent routing aur planner
- Approval-aware function-calling tool broker
- Persistent SQLite/FTS5 memory + knowledge graph
- URL/GitHub/document research ingestion
- Authorized security scope, audit logging aur constrained nmap/WhatWeb/Nikto profiles
- Continuous local VAD/STT/TTS voice runtime
- Optional local openWakeWord integration
- Particle avatar with runtime expressions aur speech-reactive animation
- Three.js/VRM renderer with phoneme-driven mouth animation
- Browser WebRTC Realtime speech-to-speech transport
- Approval-gated desktop automation primitives
- Approval-gated serial robotics primitives
- MQTT/ROS2 robotics adapters
- Semantic/embedding-backed knowledge graph support
- Runtime evaluation aur quality-signal logging
- Safe external asset provisioning
- `Hello Jenefar` -> Hinglish response preference

## Final runtime steps

Ab project ke remaining practical steps primarily runtime-side hain:

1. Local machine par wake-word assets download karo.
2. `Hi Jenefar` model ko local machine par train karo.
3. Sample VRM ko use karo ya apna licensed production VRM configure karo.
4. Target machine par live microphone, Realtime WebRTC, desktop automation aur robot hardware smoke tests run karo.
5. Actual room/microphone conditions ke according wake-word threshold tune karo.
6. False-positive aur false-reject behavior measure karke final threshold set karo.