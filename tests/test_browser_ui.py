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


def test_ui_js_has_balanced_basic_delimiters():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert js.count("(") == js.count(")")


def test_index_has_valid_script_tags_for_runtime():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<script src="/app.js"></script>' in html
    assert '<script type="module" src="/vrm.js"></script>' in html
    assert '<script src="/realtime.js"></script>' in html


def test_browser_runtime_has_single_voice_path():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "ContinuousVoiceRuntime" not in run.split("if args.voice_auto:", 1)[1].split("if args.setup_assets:", 1)[0]


def test_roman_hinglish_output_is_explicitly_enforced():
    speech = (ROOT / "jenefar" / "voice" / "speech.py").read_text(encoding="utf-8")
    browser = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    llm = (ROOT / "jenefar" / "agents" / "llm_agent.py").read_text(encoding="utf-8")
    assert "def enforce_hinglish" in speech
    assert "enforce_hinglish(reply)" in browser
    assert "LANGUAGE RULE: Output must be Roman Hinglish only." in llm


def test_browser_bridge_does_not_construct_native_audio_output():
    voice = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert "ProviderVoiceRuntime" not in voice
    assert "asyncio.run(self.voice.speak" not in voice


def test_orchestrator_does_not_append_provider_metadata_to_user_output():
    orch = (ROOT / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "provider_label" not in orch


def test_final_layout_has_dedicated_regions():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".avatar-shell{inset:0 350px 0 170px!important" in css
    assert "#activity-panel{right:20px;top:440px;width:350px" in css
    assert ".chat-glass{left:210px;top:238px;width:330px;height:330px" in css


def test_browser_speech_is_the_only_playback_path():
    bridge = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "ProviderVoiceRuntime" not in bridge
    assert "speechSynthesis" in app
    assert 'utterance.lang="en-IN"' in app


def test_dashboard_nav_buttons_have_runtime_actions():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'target=btn.dataset.nav||"home"' in js
    assert "voice:()=>document.getElementById(" in js


def test_no_internal_model_metadata_is_appended_to_spoken_output():
    orch = (ROOT / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "[Model:" not in orch


def test_browser_voice_bridge_is_serialized():
    bridge = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert "max_workers=1" in bridge


def test_dashboard_has_explicit_fixed_regions():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "Final non-overlap layout override" in css
    assert ".avatar-shell{inset:0 350px 0 170px!important" in css
    assert "#vrm-canvas{left:170px!important" in css
    assert ".holo-earth{right:350px" in css


def test_roman_hinglish_transliterates_devanagari_instead_of_dropping_it():
    from jenefar.voice.speech import enforce_hinglish

    value = enforce_hinglish("नमस्ते, मैं आपकी मदद कर सकती हूँ।")
    assert "namaste" in value.lower()
    assert "main" in value.lower()
    assert not any("\u0900" <= ch <= "\u097f" for ch in value)


def test_premium_avatar_blender_pipeline_is_wired():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    launcher = (ROOT / "jenefar" / "assets" / "premium_avatar.py").read_text(encoding="utf-8")
    blender = (ROOT / "tools" / "blender" / "premium_avatar.py").read_text(encoding="utf-8")
    vrm = (WEB / "vrm.js").read_text(encoding="utf-8")
    assert "prepare_premium_avatar" in run
    assert "JENEFAR_PREMIUM_AVATAR" in run
    assert "bpy.ops.import_scene.vrm" in blender
    assert "bpy.ops.export_scene.vrm" in blender
    assert "buildPremiumEnvironment" in vrm
    assert "JenefarPremiumEnvironment" in vrm


def test_premium_avatar_source_is_not_overwritten():
    launcher = (ROOT / "jenefar" / "assets" / "premium_avatar.py").read_text(encoding="utf-8")
    assert "shutil.copy2(source_path, temporary_input)" in launcher
    assert "Jenefar_Premium.vrm" in (ROOT / "run.py").read_text(encoding="utf-8")


def test_main_has_focused_desktop_requirements():
    desktop = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")
    assert "pyautogui>=0.9.54" in desktop


def test_main_desktop_backend_has_status_method():
    source = (ROOT / "jenefar" / "automation" / "desktop.py").read_text(encoding="utf-8")
    assert "def backend_status" in source
    assert "requirements-desktop.txt" in source


def test_python314_optional_dependency_guards_are_present():
    optional = (ROOT / "requirements-optional.txt").read_text(encoding="utf-8")
    assert 'python_version < "3.14"' in optional
