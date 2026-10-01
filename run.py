from __future__ import annotations

import argparse
import importlib.util

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jenefar modular multi-agent AI assistant"
    )
    parser.add_argument("--voice", action="store_true", help="run bounded microphone -> STT -> agent -> TTS mode")
    parser.add_argument("--voice-continuous", action="store_true", help="run continuous microphone VAD -> STT -> agent -> TTS mode")
    parser.add_argument("--text", action="store_true", help="force typed CLI mode instead of the default voice-first runtime")
    parser.add_argument("--avatar", action="store_true", help="show Jenefar's local real-time particle avatar UI")
    parser.add_argument("--realtime", action="store_true", help="launch the avatar UI for browser Realtime speech-to-speech")
    parser.add_argument("--desktop", action="store_true", help="launch Jenefar inside the optional native desktop shell")
    parser.add_argument("--avatar-port", type=int, default=8787, help="local avatar UI port")
    parser.add_argument("--discover-tools", action="store_true", help="list detected Kali/Linux tools without executing them")
    parser.add_argument("--doctor", action="store_true", help="check local Jenefar dependencies/configuration")
    parser.add_argument("--setup-vision", action="store_true", help="install the default local Ollama vision model (no hosted API required)")
    parser.add_argument("--index-file", metavar="PATH", help="index one supported text/code file into long-term memory")
    parser.add_argument("--index-dir", metavar="PATH", help="index supported text/code files under a directory")
    parser.add_argument("--index-document", metavar="PATH", help="extract PDF/DOCX/text content and index it")
    parser.add_argument("--index-url", metavar="URL", help="fetch one HTTP(S) page/API response and index it")
    parser.add_argument("--index-github", metavar="OWNER/REPO", help="fetch a public GitHub repository and index supported text/code files")
    parser.add_argument("--analyze-github", metavar="OWNER/REPO", help="summarize a public GitHub repository without executing code")
    parser.add_argument("--plan-github", metavar="OWNER/REPO", help="create a read-only repository change plan")
    parser.add_argument("--plan-task", help="task description used with --plan-github")
    parser.add_argument("--github-ref", default="main", help="GitHub branch/tag/commit")
    parser.add_argument("--github-path", action="append", default=[], help="Restrict --index-github to this file/directory path; repeatable")
    parser.add_argument("--github-max-files", type=int, default=40, help="Maximum GitHub files to index")
    parser.add_argument("--memory-search", metavar="QUERY", help="search persistent Jenefar memory/RAG index")
    parser.add_argument("--graph-search", metavar="QUERY", help="search persistent knowledge-graph relations")
    parser.add_argument("--gui-smoke-test", action="store_true", help="run a safe headless semantic GUI smoke test without pyautogui/display/model")
    parser.add_argument("--events-list", action="store_true", help="list persistent scheduled events and watchers")
    parser.add_argument("--events-run", action="store_true", help="run the persistent scheduler loop; normal tool approvals remain active")
    parser.add_argument("--events-poll-seconds", type=float, default=1.0, help="scheduler polling delay in seconds")
    parser.add_argument("--evaluation-report", action="store_true", help="show recent runtime evaluation records")
    parser.add_argument("--trace-report", action="store_true", help="show recent runtime execution traces and health summary")
    parser.add_argument("--runtime-health", action="store_true", help="show compact runtime health summary")
    parser.add_argument("--self-healing-policy", action="store_true", help="show bounded self-healing policy and safeguards")
    parser.add_argument("--provider-status", action="store_true", help="show configured online/local model provider routing without making an LLM request")
    parser.add_argument("--online-only", action="store_true", help="disable local LLM fallback for this process")
    parser.add_argument("--voice-auto", action="store_true", help="run voice mode using the configured online provider stack; falls back to OpenAI STT/TTS only when configured")
    parser.add_argument("--evaluation-dashboard", action="store_true", help="open the local evaluation dashboard")
    parser.add_argument("--setup-assets", choices=["wakeword", "avatar", "all"], help="download verified external assets into the local data directory")
    parser.add_argument("--wakeword-asset-profile", choices=["safe", "rich"], default="safe", help="wake-word asset profile: safe uses SLR26 + LibriSpeech; rich also downloads SLR28 noise/RIR data")
    parser.add_argument("--wakeword-prepare", metavar="PHRASE", help="generate an openWakeWord training config for PHRASE")
    parser.add_argument("--wakeword-prepare-validation", action="store_true", help="build the false-positive validation feature file from downloaded speech data")
    parser.add_argument("--wakeword-validation-hours", type=float, default=11.3, help="validation duration used by the openWakeWord training workflow")
    parser.add_argument("--wakeword-validation-audio", metavar="PATH", help="audio root used for wake-word validation feature extraction")
    parser.add_argument("--wakeword-config", metavar="PATH", help="training config path for --wakeword-train")
    parser.add_argument("--wakeword-train", choices=["clips", "augment", "train", "all", "tflite"], help="run a custom openWakeWord training stage")
    return parser


def prepare_avatar_model() -> "Path | None":
    """Resolve a licensed VRM source and optionally bake the premium copy."""
    import os
    from pathlib import Path

    configured_avatar = os.getenv("JENEFAR_AVATAR_VRM_PATH", "").strip()
    if configured_avatar:
        avatar_model = Path(configured_avatar).expanduser().resolve()
        if avatar_model.is_file():
            print(f"[JENEFAR] Using configured VRM avatar: {avatar_model}")
        else:
            print(
                "[JENEFAR] Configured VRM avatar not found: "
                f"{avatar_model}; falling back to the sample asset."
            )
            avatar_model = Path("data/avatar/AvatarSample_A_1.0.vrm.glb")
    else:
        avatar_model = Path("data/avatar/AvatarSample_A_1.0.vrm.glb")

    if not avatar_model.is_file():
        try:
            from jenefar.assets.provisioning import setup_avatar_asset
            avatar_model = setup_avatar_asset()
            print(f"[JENEFAR] VRM avatar ready: {avatar_model}")
        except Exception as exc:
            print(
                "[JENEFAR] VRM provisioning skipped: "
                f"{type(exc).__name__}: {exc}"
            )

    premium_output = Path("data/avatar/Jenefar_Premium.vrm")
    premium_enabled = os.getenv(
        "JENEFAR_PREMIUM_AVATAR", "1"
    ).strip().lower() not in {"0", "false", "no"}
    if avatar_model.is_file() and premium_enabled:
        try:
            from jenefar.assets.premium_avatar import prepare_premium_avatar
            baked = prepare_premium_avatar(avatar_model, premium_output)
            if baked and baked.is_file():
                avatar_model = baked
                print(f"[JENEFAR] Premium VRM avatar active: {avatar_model}")
            else:
                print(
                    "[JENEFAR] Premium Blender pipeline unavailable; "
                    "using source VRM with runtime premium styling."
                )
        except Exception as exc:
            print(
                "[JENEFAR] Premium VRM pipeline skipped safely: "
                f"{type(exc).__name__}: {exc}. Using source VRM."
            )

    return avatar_model if avatar_model.is_file() else None

def doctor() -> int:
    """Run dependency, configuration, source-syntax, and runtime smoke checks."""
    from pathlib import Path
    import ast
    import os

    print("[JENEFAR] Doctor")
    root = Path(__file__).resolve().parent
    failed = False

    # Core dependencies are required for every Jenefar mode.
    core_checks = {
        "yaml": "yaml",
        "dotenv": "dotenv",
    }
    # These are optional features; their absence must not prevent basic CLI use.
    optional_checks = {
        "openai": "openai (online LLM)",
        "sounddevice": "sounddevice (voice)",
        "pypdf": "pypdf (PDF indexing)",
        "docx": "docx (DOCX indexing)",
    }

    for module, label in core_checks.items():
        ok = importlib.util.find_spec(module) is not None
        print(f"  {label:28} {'OK' if ok else 'MISSING'}")
        failed = failed or not ok

    for module, label in optional_checks.items():
        ok = importlib.util.find_spec(module) is not None
        print(f"  {label:28} {'OK' if ok else 'OPTIONAL/MISSING'}")

    # Catch syntax errors across the project before attempting a full runtime.
    syntax_errors = []
    for path in root.rglob("*.py"):
        if any(part in {".git", "__pycache__", ".venv", "venv"} for part in path.parts):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            syntax_errors.append(f"{path.relative_to(root)}: {type(exc).__name__}: {exc}")

    if syntax_errors:
        print("  source syntax                ERROR")
        for error in syntax_errors[:20]:
            print(f"    - {error}")
        failed = True
    else:
        print("  source syntax                OK")

    try:
        from jenefar.core.config import load_config
        from jenefar.offline.connectivity import internet_available
        from jenefar.offline.local_llm import LocalLLMClient

        config = load_config()
        print(f"  config                       OK ({config.name})")
        configured_keys = any(
            os.getenv(name, "").strip()
            for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY")
        )
        print(
            "  online provider keys         "
            + ("CONFIGURED" if configured_keys else "NONE (local fallback)")
        )
        online = internet_available(timeout=0.8)
        print(f"  internet                     {'ONLINE' if online else 'OFFLINE'}")
        local_model = LocalLLMClient().detect()
        print(
            "  local model                  "
            + (f"OK ({local_model.model})" if local_model else "NOT DETECTED")
        )
        try:
            from jenefar.vision.screen import ScreenVision
            vision_base = os.getenv("JENEFAR_LOCAL_VISION_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
            vision_model = os.getenv("JENEFAR_LOCAL_VISION_MODEL", "qwen3-vl:4b").strip() or "qwen3-vl:4b"
            import json
            import urllib.request
            request = urllib.request.Request(
                f"{vision_base}/api/tags",
                headers={"User-Agent": "Jenefar/LocalVision"},
            )
            with urllib.request.urlopen(request, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            installed = [
                str(item.get("name") or item.get("model") or "")
                for item in (payload.get("models") or [])
                if isinstance(item, dict)
            ]
            markers = ("qwen3-vl", "qwen2.5vl", "llama3.2-vision", "llava", "minicpm-v", "moondream", "deepseek-ocr")
            detected_vision = next((name for name in installed if any(marker in name.lower() for marker in markers)), "")
            print(
                "  local vision                 "
                + (f"OK ({detected_vision})" if detected_vision else f"NOT READY (run: ollama pull {vision_model})")
            )
        except Exception as exc:
            print(f"  local vision                 NOT READY ({type(exc).__name__}: {exc})")

        # Import the orchestrator to catch dependency/import integration errors.
        from jenefar.core.orchestrator import JenefarOrchestrator
        print("  orchestrator import           OK")
        # Construct it only after syntax/import checks; this validates core wiring.
        JenefarOrchestrator()
        print("  orchestrator init             OK")
    except Exception as exc:
        print(f"  runtime wiring               ERROR ({type(exc).__name__}: {exc})")
        failed = True

    if failed:
        print("[JENEFAR] Doctor found core problems. Fix them before normal execution.")
        return 1
    print("[JENEFAR] Doctor checks passed. Optional features may still need extra packages.")
    return 0

def setup_vision() -> int:
    import os
    import shutil
    import subprocess
    import urllib.request
    import json

    model = os.getenv("JENEFAR_LOCAL_VISION_MODEL", "qwen3-vl:4b").strip() or "qwen3-vl:4b"
    base = os.getenv("JENEFAR_LOCAL_VISION_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    if not shutil.which("ollama"):
        print("[JENEFAR] Ollama is not installed. Install Ollama, then run: python run.py --setup-vision")
        return 1

    try:
        request = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "Jenefar/LocalVision"})
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        installed = {
            str(item.get("name") or item.get("model") or "")
            for item in (payload.get("models") or [])
            if isinstance(item, dict)
        }
    except Exception as exc:
        print(f"[JENEFAR] Ollama is not reachable at {base}: {type(exc).__name__}: {exc}")
        return 1

    vision_markers = ("qwen3-vl", "qwen2.5vl", "llama3.2-vision", "llava", "minicpm-v", "moondream", "deepseek-ocr")
    existing = next((name for name in installed if any(marker in name.lower() for marker in vision_markers)), "")
    if existing:
        print(f"[JENEFAR] Local vision model ready: {existing}")
        return 0

    print(f"[JENEFAR] Pulling local vision model: {model}")
    result = subprocess.run(
        ["ollama", "pull", model],
        text=True,
        timeout=1800,
        check=False,
    )
    if result.returncode != 0:
        print(f"[JENEFAR] Vision model setup failed with exit code {result.returncode}.")
        return result.returncode or 1

    print(f"[JENEFAR] Local vision model ready: {model}")
    return 0

def github_command(args: argparse.Namespace) -> int:
    from jenefar.coding.repository import RepositoryAnalyzer

    analyzer = RepositoryAnalyzer()

    if args.analyze_github:
        summary = analyzer.summarize(args.analyze_github, ref=args.github_ref)
        print(f"Repository: {summary.repository}@{summary.ref}")
        print(f"Default branch: {summary.default_branch}")
        print(f"Files: {len(summary.files)}")
        print(f"Languages: {summary.languages}")
        print(f"Tests: {'yes' if summary.has_tests else 'no'}")
        print(f"README: {'yes' if summary.has_readme else 'no'}")
        print(f"Entrypoints: {summary.entrypoints}")
        for item in summary.files[:50]:
            print(f"{item.category:12} {item.language:12} {item.size:8} {item.path}")
        return 0

    if not args.plan_task:
        print("[JENEFAR] --plan-github requires --plan-task")
        return 2

    plan = analyzer.plan_change(args.plan_github, args.plan_task, ref=args.github_ref)
    print(f"Repository: {plan.repository}")
    print(f"Task: {plan.task}")
    print("Likely files:")
    for path in plan.likely_files:
        print(f"  - {path}")
    print("Checks:")
    for check in plan.checks:
        print(f"  - {check}")
    print("Risks:")
    for risk in plan.risks:
        print(f"  - {risk}")
    return 0

def memory_command(args: argparse.Namespace) -> int:
    from jenefar.memory.ingest import ingest_directory, ingest_file
    from jenefar.memory.store import MemoryStore
    from jenefar.research.ingest import index_github, index_url

    store = MemoryStore()

    if args.index_file:
        added = ingest_file(args.index_file, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_file}")
        return 0

    if args.index_dir:
        added = ingest_directory(args.index_dir, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_dir}")
        return 0

    if args.index_document:
        from jenefar.docs.ingest import ingest_document
        added = ingest_document(args.index_document, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_document}")
        return 0

    if args.index_url:
        added = index_url(args.index_url, store)
        print(f"[JENEFAR] Indexed {added} chunk(s) from {args.index_url}")
        return 0

    if args.index_github:
        if args.github_max_files < 1:
            print("[JENEFAR] --github-max-files must be >= 1")
            return 2
        added = index_github(
            args.index_github,
            store,
            ref=args.github_ref,
            paths=args.github_path,
            max_files=args.github_max_files,
        )
        print(f"[JENEFAR] Indexed {added} chunk(s) from GitHub {args.index_github}@{args.github_ref}")
        return 0

    if args.memory_search:
        hits = store.search(args.memory_search, limit=8)
        if not hits:
            print("[JENEFAR] No matching memory found.")
            return 0
        for index, hit in enumerate(hits, start=1):
            print(f"\n[{index}] {hit.title}")
            print(f"source: {hit.source}")
            print(hit.content)
        return 0

    return 1

def main() -> int:
    args = build_parser().parse_args()

    if args.doctor:
        return doctor()

    if args.setup_vision:
        return setup_vision()

    if args.provider_status:
        import os
        from jenefar.core.llm import LLMClient
        from jenefar.offline.local_llm import LocalLLMClient
        client = LLMClient()
        print({
            "provider_order": client.providers.order(),
            "providers": client.provider_status("fast"),
            "local": {
                "base_url": os.getenv("JENEFAR_LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
                "model_detected": bool(LocalLLMClient().detect()),
            },
        })
        return 0

    if args.online_only:
        import os
        os.environ["JENEFAR_DISABLE_LOCAL_FALLBACK"] = "1"

    if not args.text and not any(
        getattr(args, name)
        for name in (
            "doctor", "setup_vision", "provider_status", "online_only", "voice", "voice_continuous",
            "voice_auto", "avatar", "realtime", "desktop", "discover_tools",
            "index_file", "index_dir", "index_document", "index_url", "index_github",
            "memory_search", "graph_search", "gui_smoke_test", "events_list", "events_run",
            "evaluation_report", "trace_report", "runtime_health", "self_healing_policy",
            "evaluation_dashboard", "setup_assets", "wakeword_prepare_validation",
            "wakeword_prepare", "wakeword_train", "analyze_github", "plan_github",
        )
    ):
        args.voice_auto = True

    if args.voice_auto:
        import os
        import threading
        import webbrowser
        from pathlib import Path

        from jenefar.core.orchestrator import JenefarOrchestrator
        from jenefar.voice.browser import BrowserVoiceBridge
        from jenefar.avatar.controller import AvatarController
        from jenefar.avatar.server import AvatarServer

        if args.online_only:
            os.environ["JENEFAR_DISABLE_LOCAL_FALLBACK"] = "1"

        avatar = AvatarController()
        orchestrator = JenefarOrchestrator(avatar=avatar)
        browser_voice_enabled = os.getenv("JENEFAR_BROWSER_VOICE", "1").strip().lower() not in {
            "0", "false", "no"
        }
        browser_voice = BrowserVoiceBridge(orchestrator, avatar=avatar)
        avatar_model = prepare_avatar_model()
        avatar_server = AvatarServer(
            avatar,
            port=args.avatar_port,
            vrm_path=avatar_model if avatar_model.is_file() else None,
            tool_broker=orchestrator.tool_broker,
            voice_handler=browser_voice.handle_text if browser_voice_enabled else None,
        )
        avatar_server.start()

        runtime_url = avatar_server.url
        print(f"[JENEFAR] Avatar UI: {runtime_url}")
        print(f"[JENEFAR] Avatar health: {runtime_url}health")
        print("[JENEFAR] Opening Jenefar UI in the default browser...")
        try:
            webbrowser.open(runtime_url)
        except Exception:
            print(f"[JENEFAR] Open this URL manually: {runtime_url}")

        from jenefar.voice.provider import ProviderVoiceRuntime
        audio_status = ProviderVoiceRuntime.audio_status()
        desktop_status = orchestrator.tool_broker.desktop.backend_status()
        print(
            "[JENEFAR] Browser voice runtime: avatar UI + browser microphone + "
            "multi-agent orchestrator + memory + tools."
        )
        print(
            "[JENEFAR] Desktop backend: "
            + ("READY" if desktop_status.get("pyautogui") else "UNAVAILABLE")
            + f" ({desktop_status.get('session_type') or 'unknown'}"
            + f", {desktop_status.get('screen', {}).get('width', '?')}x"
            + f"{desktop_status.get('screen', {}).get('height', '?')})"
        )
        if audio_status["stt"]:
            stt = audio_status["stt"]
            tts = audio_status["tts"]
            print(
                f"[JENEFAR] Browser STT: {stt['provider']}/{stt['model']} "
                f"fallback={','.join(stt.get('fallback', [])) or 'none'}; "
                "Browser TTS=OpenAI/Edge generated audio -> Web SpeechSynthesis fallback"
            )
        else:
            print("[JENEFAR] Backend STT provider unavailable; browser SpeechRecognition remains the input path.")

        try:
            if browser_voice_enabled:
                print("[JENEFAR] Browser microphone voice: ENABLED.")
                print("[JENEFAR] Chrome/Chromium will ask for microphone permission in the avatar UI.")
                print("[JENEFAR] Browser microphone + server-generated browser audio are the primary voice path; Web SpeechSynthesis is the final fallback.")
                print("[JENEFAR] Python TTS is disabled in this browser runtime.")
                threading.Event().wait()
            else:
                print("[JENEFAR] Browser voice is disabled. UI remains available; no terminal voice/TTS is started.")
                threading.Event().wait()
        finally:
            browser_voice.shutdown()
            avatar_server.stop()
        return 0

    if args.setup_assets:
        try:
            if args.setup_assets in {"wakeword", "all"}:
                from jenefar.assets.provisioning import setup_wakeword_assets
                result = setup_wakeword_assets(profile=args.wakeword_asset_profile)
                print(f"[JENEFAR] Wake-word assets: {result}")
            if args.setup_assets in {"avatar", "all"}:
                from jenefar.assets.provisioning import setup_avatar_asset
                path = setup_avatar_asset()
                print(f"[JENEFAR] Licensed sample VRM: {path}")
            return 0
        except Exception as exc:
            print(f"[JENEFAR] Asset setup error: {type(exc).__name__}: {exc}")
            return 1

    if args.wakeword_prepare_validation:
        try:
            from jenefar.voice.wakeword_data import prepare_validation_features
            audio_root = args.wakeword_validation_audio or "data/wakeword/assets/librispeech"
            output = prepare_validation_features(
                audio_root,
                "data/wakeword/validation_set_features.npy",
                hours=args.wakeword_validation_hours,
            )
            print(f"[JENEFAR] Wake-word validation features: {output}")
            return 0
        except Exception as exc:
            print(f"[JENEFAR] Wake-word validation error: {type(exc).__name__}: {exc}")
            return 1

    if args.wakeword_prepare:
        from jenefar.voice.wakeword_trainer import prepare_config
        path = prepare_config(
            args.wakeword_prepare,
            rich_background=args.wakeword_asset_profile == "rich",
        )
        print(f"[JENEFAR] Wake-word config: {path}")
        return 0

    if args.wakeword_train:
        if not args.wakeword_config:
            print("[JENEFAR] --wakeword-train requires --wakeword-config")
            return 2
        from jenefar.voice.wakeword_trainer import train
        return train(args.wakeword_config, stage=args.wakeword_train)

    if args.gui_smoke_test:
        try:
            from jenefar.automation.headless import HeadlessDesktopAutomation
            from jenefar.vision.screen import ScreenVision

            desktop = HeadlessDesktopAutomation()
            vision = ScreenVision(desktop)
            print("[JENEFAR] Safe headless GUI smoke test")
            print(vision.analyze("find the search box"))
            print(vision.locate_and_type("search box", "Jenefar AI"))
            print(vision.locate_and_click("submit button"))
            print(vision.analyze("verify submit"))
            print("[JENEFAR] Headless GUI smoke test completed without host GUI access.")
            return 0
        except Exception as exc:
            print(f"[JENEFAR] GUI smoke test error: {type(exc).__name__}: {exc}")
            return 1

    if args.events_list:
        try:
            from jenefar.events.engine import EventEngine
            for item in EventEngine().list():
                print(item)
            return 0
        except Exception as exc:
            print(f"[JENEFAR] Event list error: {type(exc).__name__}: {exc}")
            return 1

    if args.events_run:
        import time
        from jenefar.core.orchestrator import JenefarOrchestrator

        if args.events_poll_seconds <= 0:
            print("[JENEFAR] --events-poll-seconds must be > 0")
            return 2

        orchestrator = JenefarOrchestrator()
        print("[JENEFAR] Persistent event scheduler is running. Press Ctrl+C to stop.")
        try:
            while True:
                results = orchestrator.events.run_due(
                    orchestrator._handle_scheduled_event,
                    max_jobs=10,
                )
                for item in results:
                    print(f"[JENEFAR] Event: {item}")
                time.sleep(args.events_poll_seconds)
        except KeyboardInterrupt:
            print("[JENEFAR] Scheduler stopped.")
            return 0

    if args.evaluation_dashboard:
        import webbrowser
        from jenefar.evaluation.dashboard import render_dashboard
        dashboard_path = "data/evaluation_dashboard.html"
        from pathlib import Path
        Path(dashboard_path).write_text(render_dashboard(), encoding="utf-8")
        webbrowser.open(Path(dashboard_path).resolve().as_uri())
        print(f"[JENEFAR] Evaluation dashboard: {Path(dashboard_path).resolve()}")
        return 0

    if args.analyze_github and args.plan_github:
        print("[JENEFAR] Use only one GitHub analysis option at a time.")
        return 2

    if args.analyze_github or args.plan_github:
        try:
            return github_command(args)
        except Exception as exc:
            print(f"[JENEFAR] GitHub analysis error: {type(exc).__name__}: {exc}")
            return 1

    memory_values = [
        args.index_file,
        args.index_dir,
        args.index_document,
        args.index_url,
        args.index_github,
        args.memory_search,
        args.graph_search,
    ]
    if args.self_healing_policy:
        from jenefar.core.self_healing import SelfHealingRuntime
        runtime = SelfHealingRuntime()
        print({
            "max_attempts": runtime.policy.max_attempts,
            "base_delay_seconds": runtime.policy.base_delay_seconds,
            "max_delay_seconds": runtime.policy.max_delay_seconds,
            "circuit_threshold": runtime.circuit_threshold,
            "circuit_cooldown_seconds": runtime.circuit_cooldown_seconds,
            "transient_retry_markers": "enabled",
            "privileged_action_retries": "disabled",
        })
        return 0

    if args.trace_report or args.runtime_health:
        from jenefar.evaluation.trace import TraceStore
        store = TraceStore()
        if args.runtime_health:
            print(store.summary())
        if args.trace_report:
            for item in store.recent():
                print(item)
        return 0

    if args.evaluation_report:
        from jenefar.evaluation.loop import EvaluationLoop
        for item in EvaluationLoop().recent():
            print(item)
        return 0

    if args.graph_search:
        from jenefar.memory.graph import KnowledgeGraph
        for relation in KnowledgeGraph().search(args.graph_search):
            print(f"{relation.subject} --{relation.predicate}--> {relation.object}")
        return 0

    if any(value is not None for value in memory_values):
        if sum(value is not None for value in memory_values) != 1:
            print("[JENEFAR] Use only one memory/index option at a time.")
            return 2
        try:
            return memory_command(args)
        except Exception as exc:
            print(f"[JENEFAR] Research/memory error: {type(exc).__name__}: {exc}")
            return 1

    if args.discover_tools:
        from jenefar.tools.discovery import discover_tools
        for tool in discover_tools():
            status = "installed" if tool.installed else "missing"
            print(f"{tool.name:16} {status:9} [{tool.category}]")
        return 0

    from jenefar.core.orchestrator import JenefarOrchestrator

    if args.realtime or args.desktop:
        args.avatar = True

    avatar = None
    avatar_server = None
    browser_voice = None
    orchestrator = None

    if args.avatar:
        import webbrowser
        from jenefar.avatar.controller import AvatarController
        from jenefar.avatar.server import AvatarServer

        avatar = AvatarController()
        orchestrator = JenefarOrchestrator(avatar=avatar)

        # --avatar is a browser-first workspace too. Do not start this bridge
        # for explicit Python voice or direct Realtime mode; those own the audio path.
        if not args.realtime and not args.voice and not args.voice_continuous:
            from jenefar.voice.browser import BrowserVoiceBridge
            browser_voice = BrowserVoiceBridge(orchestrator, avatar=avatar)

        avatar_model = prepare_avatar_model()
        avatar_server = AvatarServer(
            avatar,
            port=args.avatar_port,
            vrm_path=avatar_model,
            tool_broker=orchestrator.tool_broker,
            voice_handler=browser_voice.handle_text if browser_voice else None,
        )
        avatar_server.start()
        print(f"[JENEFAR] Avatar UI: {avatar_server.url}")
        print(
            "[JENEFAR] VRM source: "
            + (str(avatar_model) if avatar_model else "unavailable; procedural fallback only")
        )
        if browser_voice is not None:
            print("[JENEFAR] Browser microphone + browser SpeechSynthesis voice path enabled.")
        if args.desktop:
            from jenefar.avatar.desktop import launch_desktop
        else:
            launch_desktop = None

        try:
            if args.desktop and launch_desktop is not None:
                launch_desktop(avatar_server.url)
            else:
                webbrowser.open(avatar_server.url)
        except Exception:
            pass
    else:
        orchestrator = JenefarOrchestrator()

    if args.voice_continuous:
        from jenefar.voice.continuous import ContinuousVoiceRuntime
        ContinuousVoiceRuntime(
            orchestrator,
            avatar=avatar,
        ).run()
        if avatar_server is not None:
            avatar_server.stop()
        return 0

    try:
        if args.voice:
            from jenefar.voice.provider import ProviderVoiceRuntime
            ProviderVoiceRuntime(
                orchestrator,
                avatar=avatar,
            ).run()
            return 0

        if args.realtime or args.avatar or args.desktop:
            if not args.desktop and args.realtime:
                print("[JENEFAR] Realtime avatar UI is running. Use the browser control to start speech-to-speech.")
            if args.desktop:
                return 0
            try:
                orchestrator.run()
            except KeyboardInterrupt:
                return 0
            return 0

        orchestrator.run()
        return 0
    finally:
        if browser_voice is not None:
            browser_voice.shutdown()
        if avatar_server is not None:
            avatar_server.stop()

if __name__ == "__main__":
    raise SystemExit(main())
