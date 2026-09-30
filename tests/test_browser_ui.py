from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "jenefar" / "avatar" / "web"


def test_premium_dashboard_has_single_workspace_markup():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.count('id="activity-panel"') == 1
    assert html.count('id="activity-connection"') == 1
    assert html.count('id="clear-workspace"') == 1
    assert html.count('id="activity-running"') == 1
    assert html.count('id="activity-queued"') == 1
    assert html.count('id="activity-done"') == 1
    assert html.count('id="activity-errors"') == 1


def test_browser_mic_starts_only_after_explicit_user_action():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "requestMicrophonePermission" in js
    assert 'navigator.mediaDevices.getUserMedia({audio:true,video:false})' in js
    assert 'micEnabled=false;' in js
    assert 'setVoiceInputStatus("CLICK MIC ON TO START",false);' in js
    assert 'micButton.onclick=async()=>{' in js


def test_browser_mic_has_recovery_for_web_speech_end_and_errors():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "recognition.onerror" in js
    assert "recognition.onend" in js
    assert "MIC PERMISSION DENIED" in js
    assert "MIC RETRYING" in js


def test_browser_voice_endpoint_is_wired():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    assert 'fetch("/voice/text"' in js
    assert 'if path == "/voice/text":' in server
    assert 'handler = self.voice_handler' in server


def test_premium_ui_has_reference_dashboard_sections():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for marker in (
        "side-nav", "chat-glass", "system-card", "quick-apps",
        "command-stack", "bottom-dock", "realtime-controls",
    ):
        assert marker in html


def test_mic_button_state_helper_and_permission_flow_are_present():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "function setMicButton(active, busy=false)" in js
    assert 'navigator.mediaDevices.getUserMedia({audio:true,video:false})' in js
    assert '.talk-button.is-active' in css
    assert '.talk-button.is-busy' in css


def test_browser_mic_reports_missing_device():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "NO MICROPHONE DEVICE FOUND" in js


def test_cinematic_scene_has_holographic_environment():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert 'id="holo-earth"' in html
    assert 'id="earth-canvas"' in html
    assert 'id="holo-particles"' in html
    assert 'function setupHolographicEnvironment' in js
    assert 'earth-canvas' in js
    assert '.holo-earth' in css
    assert '.chair-silhouette' in css


def test_interactive_controls_are_not_covered_by_decorative_layers():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert 'pointer-events:none!important' in css
    assert '.talk-button,.dock-btn,.orb-button' in css or '.talk-button' in css
    assert 'pointer-events:auto!important' in css


def test_mic_button_has_pointer_press_feedback():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'addEventListener("pointerdown"' in js
    assert 'addEventListener("pointerup"' in js
