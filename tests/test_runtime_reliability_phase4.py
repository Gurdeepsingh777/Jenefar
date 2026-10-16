from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "jenefar" / "avatar" / "web"


def test_dashboard_ids_match_runtime_and_sse_handler_is_defensive():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'id="mic-status"' in html
    assert 'document.getElementById("mic-status")' in js
    assert 'id="workspace-log"' in html
    assert 'document.getElementById("workspace-log")' in js
    assert 'id="stat-running"' in html
    assert 'document.getElementById("stat-running")' in js
    assert "if(stateEl) stateEl.textContent=stateText;" in js
    assert "if(captionEl) captionEl.textContent=event.text||caption;" in js
    assert "if(dot){" in js


def test_html_does_not_register_conflicting_mic_click_listener():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'mic.addEventListener("click"' not in html
    assert 'class="mic-label"' in html


def test_tts_quota_is_cached_for_the_runtime_session():
    voice = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert "self._openai_tts_disabled = True" in voice
    assert "credit_balance_exhausted" in voice


def test_desktop_capture_dependency_health_is_reported():
    source = (ROOT / "jenefar" / "automation" / "desktop.py").read_text(encoding="utf-8")
    assert 'status["screenshot_capture"] = True' in source
    assert 'status["screenshot_capture"] = False' in source
