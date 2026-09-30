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

Voice audio providers are selected automatically. A direct OpenAI key is preferred when available; otherwise a configured Groq key provides both STT and TTS through Groq's OpenAI-compatible audio endpoints. The active STT/TTS provider and model are printed when voice mode starts.

Continuous voice mode:

```bash
python run.py --voice-continuous
```

Continuous mode microphone ko open rakhta hai, local energy-based VAD se utterances detect karta hai, detected utterances ko STT ke liye bhejta hai, wake-word gate apply karta hai, phir same orchestrator routing use karta hai aur TTS response speakers par play karta hai.

Voice VAD ko `.env` ke `JENEFAR_VOICE_*` variables se tune kiya ja sakta hai. Groq voice ke liye `GROQ_STT_MODEL`, `GROQ_TTS_MODEL`, aur `GROQ_TTS_VOICE` configure kiye ja sakte hain.

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
├── agents/        specialist agents (including local development + Kali)
├── tools/         registry, terminal gate, Kali discovery
├── execution/     execution policy boundaries
├── memory/        SQLite/FTS5 persistent memory
├── research/      URL/GitHub ingestion aur fetching
├── workspace/     authorized local file inspection/edit/run
├── automation/    desktop/browser/media automation
├── vision/        multimodal screen understanding + semantic UI controls
├── offline/       connectivity + local-model fallback
├── capabilities/  persistent user-requested capability scope
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


## Self-update, local files aur automation

Ab Jenefar sirf questions ka answer nahi deta. User-requested local development scope ko persistent capability memory me save bhi kar sakta hai.

Example:

```text
Hello Jenefar, apne scope me local Python files ko inspect, run, debug aur user-requested feature ke liye edit karna add karo.
```

Jenefar is request ko capability scope me persist karta hai. Security authorization aur high-impact execution rules isse bypass nahi hote.

Authorized workspace roots default me current Jenefar project aur:

```text
/home/jenefar/Document/Tools
```

ko include karte hain. Extra roots `JENEFAR_WORKSPACE_ROOTS` se configure kiye ja sakte hain.

Typical local-code request:

```text
Hello Jenefar, /home/jenefar/Document/Tools/example.py check karo, run karo,
error aaye to fix karo.
```

Jenefar flow:

1. File inspect karega.
2. Existing code ko samjhega.
3. Zarurat ho to backup banayega.
4. Requested edit apply karega.
5. Diff preserve karega.
6. Python file ko run karke stdout/stderr check karega.
7. Final result clearly report karega.

Code modification aur Python execution explicit approval gate ke peeche hain; isse accidental arbitrary execution se protection milti hai.

## Dedicated Kali specialist

Kali/Linux requests ke liye dedicated `kali` specialist aur curated tool catalog add kiya gaya hai.

Catalog me current common security workflows ke saath tactic-style metadata diya gaya hai, jaise:

- Reconnaissance
- Resource Development
- Initial Access
- Execution
- Privilege Escalation
- Credential Access
- Discovery
- Lateral Movement
- Collection
- Command and Control
- Forensics

Kali ke official metapackage ecosystem me information gathering, vulnerability, web, passwords, wireless, exploitation, post-exploitation, forensics, reverse-engineering, fuzzing, hardware aur sniffing/spoofing jaise tool groups available hain. citeturn525427search0turn525427search1

Example:

```text
Hello Jenefar, Kali me nmap use karke mere authorized lab target ko check karo.
```

Network/security execution ke liye `authorized_targets` scope aur explicit approval dono apply hote hain.

Dedicated Kali model configure karna ho to:

```env
JENEFAR_KALI_MODEL=
```

blank chhoda ja sakta hai; tab normal online model/local model fallback use hoga.

## Online-first, offline fallback

Jenefar runtime connectivity detect karta hai.

Flow:

```text
Internet available
    ↓
Online model + online tools
    ↓
Internet unavailable
    ↓
Local OpenAI-compatible model
    ↓
Local tools continue
```

Local fallback ke liye Ollama ya llama.cpp jaise OpenAI-compatible local servers use kiye ja sakte hain. Ollama local `/v1/chat/completions` compatibility provide karta hai, aur llama.cpp OpenAI-compatible server ke saath tool calling support karta hai. citeturn881519search7turn881519search0turn881519search1

Environment:

```env
JENEFAR_LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
JENEFAR_LOCAL_LLM_MODEL=
```

Model name blank hone par Jenefar local server se available model discover karta hai.

Offline condition me online-only capabilities ki list explicitly show ki ja sakti hai, jaise:

- Web search
- Remote downloads
- YouTube
- Online song recognition
- Live GitHub retrieval

Local file inspection, local Python execution, local media playback aur local model inference continue reh sakte hain.

## YouTube, browser aur song recognition

Browser selection automatically:

```text
Firefox
  ↓
Google Chrome / Chromium
  ↓
xdg-open
```

YouTube request me Jenefar optional `yt-dlp` backend ke through first search result ka video URL resolve karke preferred browser me open kar sakta hai; backend unavailable hone par YouTube search page fallback hota hai.

Example:

```text
Hello Jenefar, YouTube par [song name] play karo.
```

Agar user kisi phone/device se song chala raha ho:

```text
Hello Jenefar, jo song main abhi baja raha hun use identify karo.
```

to optional microphone recognition backend short audio sample capture karke online recognition service se track identify kar sakta hai. ShazamIO current Python package file/bytes se track recognition support karta hai. citeturn599676search1turn599676search7

Ye feature internet ke bina unavailable rahega aur offline notice me list ho jayega.

## Local MP3 playback

Example:

```text
Hello Jenefar, /home/music ke andar Osho folder me jao aur first MP3 VLC se play karo.
```

Jenefar authorized local folder ko inspect karke matching folder aur first MP3 identify kar sakta hai, phir VLC se playback start karta hai.

## Offline list close

Agar offline notice/list show hui ho aur user bole:

```text
Maine padh liya, list close kar do.
```

to Jenefar offline notice acknowledgement tool use karke us notice ko close kar sakta hai.

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

## Phase 1 — Hierarchical Planning, Model Routing aur Self-Healing Coding

Phase 1 me Jenefar compound requests ke liye bounded multi-step execution plan banata hai. Local Python repair work ke liye normal flow inspect → baseline validation/run → diagnose → repair → retest → report hai. Failure aane par specialist configured repair-attempt limit ke andar diagnosis aur retest continue kar sakta hai.

Model routing role-based hai: coding (local development, Python, repository), security (Kali, cybersecurity, bug-bounty), research, robotics, automation, aur fast/general. Online profiles JENEFAR_MODEL_* aur optional local profiles JENEFAR_LOCAL_LLM_MODEL_* se override kiye ja sakte hain. Unset profiles global model configuration par fall back karte hain.

Local edits, Python execution aur pytest ab bhi authorized workspace aur explicit approval boundaries ke andar hi hote hain.


## Phase 2 — Vision, GUI Agent aur Semantic Screen Control

Phase 2 me Jenefar ko semantic desktop understanding add ki gayi hai. GUI specialist current screen ko screenshot ke through multimodal vision backend ko deta hai aur visible UI elements ko label, role, confidence, bounding box aur center coordinates ke saath normalize karta hai.

Semantic tools:
- desktop_observe — current screen ko vision model se analyze karta hai.
- desktop_find_element — semantic query se visible UI element locate karta hai.
- desktop_click_element — element ko semantic description se locate karke click karta hai.
- desktop_type_into_element — semantic input field locate, click aur text type karta hai.
- desktop_hotkey — bounded safe keyboard shortcuts.
- desktop_scroll — bounded scrolling.

GUI actions explicit approval ke peeche rehte hain. Screen observation bhi GUI action policy ke through gated hai, kyunki screenshot me private information ho sakti hai.

Vision flow:

User goal
   ↓
GUI Vision Agent
   ↓
Current screenshot
   ↓
Vision model
   ↓
Semantic elements
   ↓
Validated coordinates
   ↓
Approved GUI action
   ↓
Optional re-observation / verification

Online mode me configured JENEFAR_VISION_MODEL use hota hai; blank hone par OPENAI_MODEL fallback use hota hai. Offline mode me JENEFAR_LOCAL_VISION_MODEL ya compatible local multimodal model use hota hai.

Bounding boxes model ke resized screenshot coordinates se original desktop resolution me scale kiye jate hain aur screen boundaries ke against validate kiye jate hain.

Example requests:

Hello Jenefar, screen par search box find karo.
Hello Jenefar, search box me Jenefar AI type karo.
Hello Jenefar, jo Submit button screen par hai use click karo.

Current implementation semantic coordinates ko model output se derive karti hai; live desktop smoke-testing ke liye target machine par pyautogui aur vision-capable model configured hona zaroori hai.


## Phase 3 — Dynamic Skills aur Universal Connector Layer

Phase 3 me Jenefar ka extension architecture modular banaya gaya hai. Skills ab persistent enable/disable state ke saath declarative manifests ke form me manage ho sakti hain, aur service integrations ko central connector gateway ke through expose kiya gaya hai.

### Dynamic skills

Built-in skills me `local_development`, `gui_vision`, `browser_media`, `github_research`, `robotics`, `security` aur `research` shamil hain. `SkillManager` inki enabled state ko `data/skills.json` me persist karta hai.

New declarative skill add karne ke liye `.json` manifest ko configured `JENEFAR_SKILL_ROOTS` directory me rakho. Manifest sirf metadata, keywords, permissions, connector dependencies aur optional system guidance define karta hai; arbitrary Python plugin code automatically execute nahi hota.

Example natural-language commands:

```text
Hello Jenefar, available skills dikhao.
Hello Jenefar, GUI vision skill enable karo.
Hello Jenefar, GUI vision skill disable karo.
Hello Jenefar, Blender skill manifest install karo.
```

Skill disable hone par planner us specialist ko directly use nahi karta aur enabled `research` skill par safe fallback karta hai. Skill enablement security authorization ko bypass nahi karta.

### Universal connector layer

`ConnectorManager` trusted adapters ko ek common interface deta hai. Current built-in connectors me:
- `workspace` — authorized local file/directory reads
- `browser` — public URL aur YouTube browser actions
- `web` — public HTTP(S) read-only fetching
- `github` — public GitHub repository reads
- `robotics` — serial robotics
- `mqtt` — robotics telemetry/commands
- `ros2` — ROS2 topic discovery/publication
- `security` — existing scoped security boundary

Natural-language model tools `connector_catalog`, `connector_status` aur approval-gated `connector_execute` ke through is layer ko use karte hain.

Online-required connectors internet unavailable hone par execute nahi karte aur explicit connection error return karte hain. Connector actions centralized audit log me record hote hain.

Architecture:

```text
User Goal
   ↓
Agent / Planner
   ↓
Skill Registry
   ↓
Universal Connector Gateway
   ↓
Trusted Adapter
   ↓
Tool / Service
```

Is architecture ka main purpose ye hai ki nayi service integration ko core orchestrator ke andar hard-code karne ki jagah ek isolated connector adapter me add kiya ja sake.


## Phase 4 — Safe Headless GUI Validation, Layered Memory/RAG aur Event Scheduler

Phase 4 ne Phase 2 ke live-desktop dependency ko safe virtual backend se close kiya hai. Server/CI machine par:

~~~env
JENEFAR_DESKTOP_BACKEND=headless
~~~

set karne par Jenefar deterministic virtual screen fixtures use karta hai. Ye backend pyautogui, real display, mouse, keyboard ya configured vision model ko access nahi karta. Semantic observe → locate → click/type → verify path wahi rehta hai jo live GUI flow use karta hai.

Safe smoke test:

~~~bash
python run.py --gui-smoke-test
~~~

Live machine par JENEFAR_DESKTOP_BACKEND=native hone par existing pyautogui + configured online/local multimodal vision path use hota hai.

### Layered memory/RAG

Local SQLite memory ab in layers ko support karti hai:

- episodic — conversation/session events
- semantic — durable facts
- procedural — reusable playbooks

Retrieval lexical FTS + optional local embeddings + importance + time-decay + access recency fuse karti hai. Embeddings optional hain; embedding package/model unavailable hone par lexical/recency retrieval continue hoti hai.

Procedural memory execute nahi hoti; wo reusable steps aur constraints ke roop me store hoti hai. memory_procedure_save sirf playbook save karta hai, execution nahi.

### Persistent scheduler/event engine

Supported trigger types:

~~~text
once
interval (minimum 60 seconds)
daily (HH:MM + IANA timezone)
watch (explicit application event + optional exact payload filters)
~~~

CLI:

~~~bash
python run.py --events-list
python run.py --events-run
~~~

Scheduled prompts Jenefar ke normal orchestrator path se run hote hain. Scheduler tool confirmation ya authorized-security boundaries ko bypass nahi karta. Scheduled prompt me koi approval-gated action ho to existing approval workflow hi apply hota hai.

Natural-language examples:

~~~text
Hello Jenefar, every day 09:00 par mujhe Python practice yaad dilana.
Hello Jenefar, jab download.finished event aaye tab mujhe summary dena.
Hello Jenefar, mera ESP32 debugging procedure memory me save karo.
~~~

Phase 4 data local data/jenefar_memory.db aur data/events.db me persist hota hai.


## Phase 5 — Runtime Intelligence, Traceability & Diagnostics

Phase 5 adds a structured execution trace around every orchestrator request. Each task gets a trace ID correlated with the session and optional scheduler event, and records planner intent, selected/actual specialist, model role, connectivity, approval-gated tool calls, verification outcome, latency, errors and final status.

Runtime quality evaluation now consumes these structured signals instead of looking only at final text. This produces richer quality records while keeping evaluation observational: it does not rewrite code, weaken approval policy, or auto-execute stored procedures.

Runtime diagnostics are available from the CLI:

```bash
python run.py --runtime-health
python run.py --trace-report
python run.py --evaluation-report
python run.py --evaluation-dashboard
```

The evaluation dashboard now includes both quality evaluations and recent execution traces, including latency, agents, providers, approvals and tool counts.

Trace data is local append-only JSONL under `data/execution_traces.jsonl`. It is intended for local diagnostics and can be removed without affecting Jenefar's core memory or scheduler state.


## Phase 6 — Self-Healing Runtime & Reliability

Phase 6 adds bounded runtime recovery for transient failures. Jenefar can retry safe, read-oriented agent dispatches when a timeout, temporary connection failure, rate limit, or transient service error occurs.

Recovery is deliberately conservative:

- Maximum retry attempts are bounded.
- Exponential backoff is capped.
- Security specialists (kali, cybersecurity, bugbounty) are never automatically retried.
- Approval-gated or state-changing operations are never automatically retried.
- Terminal, file-edit/write/delete, robotics, MQTT/ROS2, desktop-action and connector actions are excluded from automatic retries.
- Repeated transient failures open a short runtime circuit breaker to prevent retry storms.
- Runtime traces record the self-healing retry counters.

Diagnostics:

```bash
python run.py --self-healing-policy
python run.py --runtime-health
python run.py --trace-report
```

The self-healing layer is recovery-only. It does not grant permissions, change authorized security targets, auto-approve tools, or weaken existing execution policies.

## Kali Linux quick start

Jenefar ko fresh Kali Linux machine par verify karne ke liye:

~~~bash
git clone https://github.com/Gurdeepsingh777/Jenefar.git
cd Jenefar

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

python run.py --doctor
python run.py
~~~

`--doctor` core dependencies, project Python syntax, configuration, orchestrator imports/init, internet connectivity aur local LLM detection check karta hai. Voice/PDF/DOCX packages optional hain; unke missing hone se basic CLI ko fail nahi kiya jata.

Online OpenAI mode ke liye:

~~~bash
export OPENAI_API_KEY="your_api_key"
python run.py
~~~

Local/offline mode ke liye Ollama ya kisi OpenAI-compatible local LLM server ko start karke `python run.py` chala sakte ho.

Agar sirf CLI/dependency verification karni ho, `python run.py --doctor` sufficient hai.
## Multi-provider LLM failover

Jenefar can use multiple online LLM providers and automatically move to the next configured provider when a request fails because of authentication, rate limiting, timeout, connection, or service-availability errors.

Recommended configuration:

```env
JENEFAR_PROVIDER_ORDER=openai,openrouter,gemini,groq,cerebras
JENEFAR_PROVIDER_COOLDOWN_SECONDS=60

OPENAI_API_KEY=
OPENAI_MODEL=

OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-lite

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

CEREBRAS_API_KEY=
CEREBRAS_MODEL=gpt-oss-120b
```

Provider-specific model variables may also be set per role, for example:

```env
JENEFAR_OPENROUTER_MODEL_CODING=
JENEFAR_GROQ_MODEL_FAST=
JENEFAR_GEMINI_MODEL_RESEARCH=
```

The provider order is evaluated left-to-right. A provider that repeatedly fails with a retryable error enters a short cooldown so Jenefar does not repeatedly hammer a rate-limited or unavailable endpoint. If every online provider fails, the existing Ollama/OpenAI-compatible local model remains the final fallback unless `JENEFAR_DISABLE_LOCAL_FALLBACK=1` or `python run.py --online-only` is used.

Check configuration without sending an LLM request:

```bash
python run.py --provider-status
```

API keys are read from environment variables and are never printed by provider status.

Official provider pages:

- OpenRouter: https://openrouter.ai/
- Google Gemini API: https://ai.google.dev/gemini-api
- Groq: https://console.groq.com/
- Cerebras: https://inference-docs.cerebras.ai/

Free-tier availability, quotas, and model availability can change by provider and account; choose models from the provider's current documentation rather than assuming a model remains free.

## Model/provider configuration

Jenefar supports an online-first model setup so your Kali CPU does not carry the full LLM workload when an OpenAI API key is configured. Put secrets only in `.env` (never commit them):

~~~bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=your_model_here
JENEFAR_MODEL_FAST=your_fast_model_here
JENEFAR_MODEL_CODING=your_coding_model_here
JENEFAR_MODEL_RESEARCH=your_research_model_here
~~~

Role-specific variables override `OPENAI_MODEL`. When `OPENAI_API_KEY` is unavailable or the online provider cannot be reached, Jenefar falls back to the detected local OpenAI-compatible model (for example Ollama).

