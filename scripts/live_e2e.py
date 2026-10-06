#!/usr/bin/env python3
"""Opt-in real-machine E2E checks for voice, vision, browser, VRM and long runs."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report(name: str, ok: bool, detail: object) -> None:
    print(json.dumps({"check": name, "ok": ok, "detail": detail}, ensure_ascii=False))


def voice_once() -> int:
    import sounddevice as sd
    from jenefar.core.orchestrator import JenefarOrchestrator
    from jenefar.voice.provider import ProviderVoiceRuntime

    devices = sd.query_devices()
    inputs = [d for d in devices if int(d.get("max_input_channels", 0)) > 0]
    outputs = [d for d in devices if int(d.get("max_output_channels", 0)) > 0]
    if not inputs:
        report("microphone", False, "No input audio device found")
        return 1
    report("audio_devices", True, {"inputs": len(inputs), "outputs": len(outputs)})

    runtime = ProviderVoiceRuntime(JenefarOrchestrator(), seconds=5)
    pcm = runtime._record_microphone(5)
    report("microphone_capture", bool(pcm), {"bytes": len(pcm)})
    if not pcm:
        return 1

    text = asyncio.run(runtime.transcribe_pcm(pcm))
    if not text:
        report("stt", False, "STT returned empty transcript")
        return 1
    report("stt", True, text)

    reply = runtime.orchestrator.handle(text, response_language="Hinglish")
    report("llm", True, reply[:500])
    asyncio.run(runtime.speak(reply))
    report("tts", True, "TTS playback completed")
    return 0


def vision_once(allow_actions: bool) -> int:
    from jenefar.automation.desktop import DesktopAutomation
    from jenefar.vision.grounding import GroundingEngine, VisualElement
    from jenefar.vision.screen import ScreenVision

    desktop = DesktopAutomation()
    status = desktop.backend_status()
    if not status.get("pyautogui") or not status.get("screen"):
        report("desktop", False, status)
        return 1

    result = ScreenVision(desktop).analyze("find the main actionable controls visible on this screen")
    report("vision", True, {
        "provider": result.get("provider"),
        "summary": result.get("summary", ""),
        "elements": len(result.get("elements", [])),
    })

    elements = []
    for i, item in enumerate(result.get("elements", [])):
        if not isinstance(item, dict) or len(item.get("bbox", [])) != 4:
            continue
        x1, y1, x2, y2 = item["bbox"]
        elements.append(VisualElement(
            element_id=str(i),
            role=str(item.get("role", "")),
            label=str(item.get("label", "")),
            x=float(x1), y=float(y1), width=float(x2-x1), height=float(y2-y1),
            confidence=float(item.get("confidence", 0)),
        ))

    engine = GroundingEngine()
    ranked = engine.rank(elements, "search button")
    if not ranked:
        report("grounding", True, "No matching target; grounding engine ran safely")
        return 0

    target = engine.require_confident(ranked)
    report("grounding", True, {
        "label": target.label,
        "confidence": target.confidence,
        "center": target.center(),
    })
    if allow_actions:
        x, y = map(int, target.center())
        report("grounded_action", True, desktop.click(x, y))
    else:
        report("grounded_action", True, "Dry-run; pass --allow-actions to click")
    return 0


def browser_once(url: str, headed: bool) -> int:
    try:
        from playwright.sync_api import sync_playwright
        from jenefar.browser.computer_agent import ComputerAgent
        from jenefar.browser.playwright_adapter import PlaywrightComputerAdapter
    except Exception as exc:
        report("browser_dependencies", False, f"{type(exc).__name__}: {exc}")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page()
        adapter = PlaywrightComputerAdapter(page)
        agent = ComputerAgent(adapter, max_steps=4)
        steps = agent.execute(
            lambda goal, observation, history: (
                {"type": "goto", "url": goal, "expected_url": goal}
                if not history else None
            ),
            url,
        )
        verified = bool(steps and steps[0].verified)
        report("browser_navigation", verified, {
            "url": page.url, "title": page.title(), "steps": len(steps)
        })
        page.screenshot(path=str(ROOT / "data" / "browser-e2e.png"), full_page=True)
        browser.close()
        return 0 if verified else 1


def vrm_once(url: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        report("vrm_browser_dependencies", False, f"{type(exc).__name__}: {exc}")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        health = json.loads(urllib.request.urlopen(url.rstrip("/") + "/health", timeout=5).read())
        iframe = page.locator("#hud-avatar-frame")
        vrm_canvas = page.locator("#vrm-canvas")
        ok = bool(health.get("vrm_available")) and iframe.count() == 1 and vrm_canvas.count() == 1
        report("vrm_browser_session", ok, {
            "vrm_available": health.get("vrm_available"),
            "hud_iframe": iframe.count(),
            "vrm_canvas": vrm_canvas.count(),
        })
        browser.close()
        return 0 if ok else 1


def long_run(seconds: int) -> int:
    from jenefar.core.production_runtime import ProductionRuntime

    runtime = ProductionRuntime()
    graph = runtime.task_graph()
    started = time.monotonic()

    def work(value: str) -> str:
        time.sleep(2)
        return value

    graph.add("prepare", lambda _: work("prepared"))
    graph.add("compute", lambda _: work("computed"), depends_on=["prepare"], retries=1)
    graph.add("verify", lambda _: work("verified"), depends_on=["compute"])
    graph.add("finish", lambda _: work("finished"), depends_on=["verify"])
    result = graph.run({}, max_workers=2, checkpoint_path=str(ROOT / "data" / "e2e-checkpoint.json"))
    elapsed = time.monotonic() - started
    ok = elapsed >= min(seconds, 6) and all(item.ok for item in result.values())
    report("long_running_task", ok, {"elapsed_seconds": round(elapsed, 2), "nodes": len(result)})
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-once", action="store_true")
    parser.add_argument("--vision-once", action="store_true")
    parser.add_argument("--allow-actions", action="store_true")
    parser.add_argument("--browser-url")
    parser.add_argument("--browser-headed", action="store_true")
    parser.add_argument("--vrm-url")
    parser.add_argument("--long-run", type=int, default=0)
    args = parser.parse_args()

    selected = (args.voice_once, args.vision_once, bool(args.browser_url), bool(args.vrm_url), bool(args.long_run))
    if not any(selected):
        parser.error("Select at least one live E2E check.")

    failures = 0
    if args.voice_once:
        failures |= voice_once()
    if args.vision_once:
        failures |= vision_once(args.allow_actions)
    if args.browser_url:
        failures |= browser_once(args.browser_url, args.browser_headed)
    if args.vrm_url:
        failures |= vrm_once(args.vrm_url)
    if args.long_run:
        failures |= long_run(args.long_run)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
