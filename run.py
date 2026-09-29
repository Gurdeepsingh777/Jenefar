from __future__ import annotations

import argparse
import importlib.util

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jenefar modular multi-agent AI assistant"
    )
    parser.add_argument("--voice", action="store_true", help="run bounded microphone -> STT -> agent -> TTS mode")
    parser.add_argument("--voice-continuous", action="store_true", help="run continuous microphone VAD -> STT -> agent -> TTS mode")
    parser.add_argument("--avatar", action="store_true", help="show Jenefar's local real-time particle avatar UI")
    parser.add_argument("--realtime", action="store_true", help="launch the avatar UI for browser Realtime speech-to-speech")
    parser.add_argument("--desktop", action="store_true", help="launch Jenefar inside the optional native desktop shell")
    parser.add_argument("--avatar-port", type=int, default=8787, help="local avatar UI port")
    parser.add_argument("--discover-tools", action="store_true", help="list detected Kali/Linux tools without executing them")
    parser.add_argument("--doctor", action="store_true", help="check local Jenefar dependencies/configuration")
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

def doctor() -> int:
    print("[JENEFAR] Doctor")
    checks = {
        "yaml": "yaml",
        "dotenv": "dotenv",
        "openai": "openai",
        "sounddevice": "sounddevice",
        "pypdf": "pypdf",
        "docx": "docx",
    }
    failed = False
    for label, module in checks.items():
        ok = importlib.util.find_spec(module) is not None
        print(f"  {label:12} {'OK' if ok else 'MISSING'}")
        failed = failed or not ok

    try:
        from jenefar.core.config import load_config
        from jenefar.offline.connectivity import internet_available
        from jenefar.offline.local_llm import LocalLLMClient
        config = load_config()
        online = internet_available()
        local_model = LocalLLMClient().detect()
        print(f"  config       OK ({config.name})")
        print(f"  api key      {'SET' if __import__('os').getenv('OPENAI_API_KEY') else 'NOT SET'}")
        print(f"  internet     {'ONLINE' if online else 'OFFLINE'}")
        print(f"  local model  {'OK (' + local_model.model + ')' if local_model else 'NOT DETECTED'}")
    except Exception as exc:
        print(f"  config       ERROR ({type(exc).__name__}: {exc})")
        failed = True

    if failed:
        print("[JENEFAR] Doctor found missing/invalid local dependencies.")
        return 1
    print("[JENEFAR] Doctor checks passed.")
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
    orchestrator = None

    if args.avatar:
        import webbrowser
        from jenefar.avatar.controller import AvatarController
        from jenefar.avatar.server import AvatarServer

        avatar = AvatarController()
        orchestrator = JenefarOrchestrator(avatar=avatar)
        avatar_server = AvatarServer(
            avatar,
            port=args.avatar_port,
            tool_broker=orchestrator.tool_broker,
        )
        avatar_server.start()
        print(f"[JENEFAR] Avatar UI: {avatar_server.url}")
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
            from jenefar.voice.openai_voice import OpenAIVoiceRuntime
            OpenAIVoiceRuntime(
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
        if avatar_server is not None:
            avatar_server.stop()

if __name__ == "__main__":
    raise SystemExit(main())
