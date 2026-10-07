#!/usr/bin/env python3
"""Single-command real-machine acceptance suite for Jenefar.

Safe by default:
- runs the complete unit/integration test suite;
- runs final machine acceptance;
- verifies full-screen capture is denied by default;
- starts/reuses the local avatar server and checks protected runtime endpoints;
- verifies the real Chromium/DOM path without taking screenshots;
- exercises the production task graph;
- optionally exercises the real microphone/STT/LLM/TTS path.

Use --voice only when a microphone and audio output are available.
This suite never enables JENEFAR_ALLOW_SCREEN_CAPTURE.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv" / "bin" / "python")
AVATAR_HOST = os.getenv("JENEFAR_HOST", "127.0.0.1")
AVATAR_PORT = int(os.getenv("JENEFAR_AVATAR_PORT", "8787"))
AVATAR_URL = f"http://{AVATAR_HOST}:{AVATAR_PORT}"

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: object, *, required: bool = True) -> None:
    RESULTS.append({"check": name, "ok": bool(ok), "required": required, "detail": detail})
    mark = "PASS" if ok else ("SKIP" if not required else "FAIL")
    print(f"[{mark}] {name}: {detail}")


def run_cmd(name: str, args: list[str], timeout: int = 120) -> bool:
    try:
        p = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = ((p.stdout or "") + (p.stderr or "")).strip()
        check(name, p.returncode == 0, output[-1200:])
        return p.returncode == 0
    except Exception as exc:
        check(name, False, f"{type(exc).__name__}: {exc}")
        return False


def http_json(path: str, timeout: int = 5) -> tuple[int, object]:
    url = AVATAR_URL + path
    request = urllib.request.Request(url, headers={"User-Agent": "Jenefar-E2E/1"})
    user = os.getenv("JENEFAR_AUTH_USER", "")
    password = os.getenv("JENEFAR_AUTH_PASSWORD", "")
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        try:
            return response.status, json.loads(raw)
        except json.JSONDecodeError:
            return response.status, raw


def ensure_avatar() -> subprocess.Popen | None:
    try:
        status, payload = http_json("/health", timeout=1)
        if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
            check("avatar_process", True, "existing Jenefar avatar server is healthy")
            return None
    except Exception:
        pass

    try:
        proc = subprocess.Popen(
            [PYTHON, "run.py", "--avatar"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except Exception as exc:
        check("avatar_process", False, f"could not start avatar: {type(exc).__name__}: {exc}")
        return None

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            status, payload = http_json("/health", timeout=1)
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                check("avatar_process", True, "started local avatar server")
                return proc
        except Exception:
            time.sleep(0.25)

    proc.terminate()
    check("avatar_process", False, "avatar did not become healthy within 20 seconds")
    return None


def privacy_check() -> None:
    from jenefar.automation.desktop import DesktopAutomation

    old = os.environ.pop("JENEFAR_ALLOW_SCREEN_CAPTURE", None)
    try:
        desktop = DesktopAutomation(ROOT / "data" / "screenshots")
        try:
            desktop.capture_frame()
        except PermissionError as exc:
            check("screen_privacy_default", True, str(exc))
        else:
            check("screen_privacy_default", False, "full-screen capture unexpectedly succeeded")
    finally:
        if old is not None:
            os.environ["JENEFAR_ALLOW_SCREEN_CAPTURE"] = old


def browser_dom_check() -> None:
    try:
        from playwright.sync_api import sync_playwright
        from jenefar.browser.playwright_adapter import PlaywrightComputerAdapter
    except Exception as exc:
        check("browser_dom", False, f"{type(exc).__name__}: {exc}")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        adapter = PlaywrightComputerAdapter(page)
        page.set_content(
            "<main><label for='name'>Name</label>"
            "<input id='name'><button>Run</button>"
            "<div id='result'>idle</div></main>"
        )
        adapter.act({"type": "fill", "label": "Name", "value": "Jenefar"})
        adapter.act({"type": "click_role", "role": "button", "name": "Run"})
        page.locator("#result").evaluate("(e) => e.textContent = document.querySelector('#name').value")
        observation = adapter.observe()
        ok = "Jenefar" in observation["text"]
        check("browser_dom", ok, {
            "url": observation["url"],
            "title": observation["title"],
            "text_contains_janefar": ok,
        })
        browser.close()


def avatar_checks() -> None:
    for name, path in (
        ("avatar_health", "/health"),
        ("avatar_runtime_status", "/runtime/status"),
        ("avatar_runtime_metrics", "/runtime/metrics"),
        ("avatar_readiness", "/production/readiness"),
    ):
        try:
            status, payload = http_json(path)
            ok = status == 200 and isinstance(payload, (dict, list))
            if path == "/health":
                ok = ok and isinstance(payload, dict) and payload.get("status") == "ok"
            check(name, ok, {"status": status, "payload": payload})
        except Exception as exc:
            check(name, False, f"{type(exc).__name__}: {exc}")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        check("avatar_ui_dom", False, f"{type(exc).__name__}: {exc}")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        user = os.getenv("JENEFAR_AUTH_USER", "")
        password = os.getenv("JENEFAR_AUTH_PASSWORD", "")
        if user and password:
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            page.set_extra_http_headers({"Authorization": f"Basic {token}"})
        try:
            page.goto(AVATAR_URL + "/", wait_until="domcontentloaded", timeout=10000)
            selectors = {
                "vrm_canvas": "#vrm-canvas",
                "hud_avatar": "#hud-avatar-frame",
                "system_card": ".system-card",
                "activity_panel": "#activity-panel",
            }
            found = {name: page.locator(selector).count() for name, selector in selectors.items()}
            ok = all(value >= 1 for value in found.values())
            check("avatar_ui_dom", ok, found)
        except Exception as exc:
            check("avatar_ui_dom", False, f"{type(exc).__name__}: {exc}")
        finally:
            browser.close()


def voice_check() -> None:
    ok = run_cmd("voice_e2e", [PYTHON, "scripts/live_e2e.py", "--voice-once"], timeout=90)
    if not ok:
        return


def long_run_check() -> None:
    run_cmd(
        "long_running_task",
        [PYTHON, "scripts/live_e2e.py", "--long-run", "6"],
        timeout=30,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", action="store_true", help="run real microphone -> STT -> LLM -> TTS")
    args = parser.parse_args()

    if not Path(PYTHON).exists():
        check("python_venv", False, f"missing {PYTHON}")
        return 1

    run_cmd("pytest", [PYTHON, "-m", "pytest", "-q"], timeout=180)
    run_cmd("final_acceptance", [PYTHON, "scripts/final_acceptance.py"], timeout=90)

    privacy_check()
    browser_dom_check()

    avatar_proc = ensure_avatar()
    if avatar_proc is not None or _avatar_is_healthy():
        avatar_checks()
    else:
        check("avatar_checks", False, "avatar server unavailable", required=False)

    long_run_check()

    if args.voice:
        voice_check()
    else:
        check("voice_e2e", True, "not run; use --voice to exercise microphone/STT/LLM/TTS", required=False)

    failures = [x for x in RESULTS if x["required"] and not x["ok"]]
    print("\n" + "=" * 72)
    print(json.dumps({
        "ok": not failures,
        "required_failures": [x["check"] for x in failures],
        "checks": RESULTS,
    }, indent=2, ensure_ascii=False, default=str))
    print("=" * 72)

    if avatar_proc is not None:
        avatar_proc.terminate()
        try:
            avatar_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            avatar_proc.kill()

    return 1 if failures else 0


def _avatar_is_healthy() -> bool:
    try:
        status, payload = http_json("/health", timeout=1)
        return status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
