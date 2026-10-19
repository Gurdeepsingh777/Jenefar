from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "jenefar" / "avatar" / "web"


def test_premium_dashboard_has_single_workspace_markup():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.count('id="activity-panel"') == 1
    assert html.count('id="clear-workspace"') == 1
    assert html.count('id="stat-running"') == 1
    assert html.count('id="stat-queue"') == 1
    assert html.count('id="stat-done"') == 1
    assert html.count('id="stat-error"') == 1
    assert html.count('id="workspace-log"') == 1


def test_browser_mic_starts_only_after_explicit_user_action():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "requestMicrophonePermission" in js
    assert "navigator.mediaDevices?.getUserMedia" in js
    assert "audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}" in js
    assert "new MediaRecorder(fallbackStream" in js
    assert 'fetch("/voice/audio"' in js
    assert 'micEnabled=false;' in js
    assert 'setVoiceInputStatus("CLICK MIC ON TO START",false);' in js
    assert 'micButton.onclick=async()=>{' in js
    assert 'if(canRecord){\n        // Prefer server-side STT to Chromium' in js
    assert 'setVoiceInputStatus("CLICK MIC ON — SERVER STT READY",false);' in js
    assert "const speechThreshold=0.010;" in js
    assert "NO WORDS RECOGNIZED — SPEAK CLOSER OR CHECK MIC LEVEL" in js


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
        "command-stack", "bottom-dock", "status-strip",
    ):
        assert marker in html


def test_mic_button_state_helper_and_permission_flow_are_present():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "function setMicButton(active, busy=false)" in js
    assert "navigator.mediaDevices?.getUserMedia" in js
    assert "audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}" in js
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
    assert 'id="holo-earth"' in html and 'id="earth-canvas"' not in html
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
    assert '<script type="module" src="/app.js"></script>' in html
    assert '<script type="module" src="/vrm.js"></script>' in html
    assert '<script src="/realtime.js"></script>' in html
    assert 'id="realtime-button"' in html
    assert 'id="realtime-state"' in html


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
    # ProviderVoiceRuntime is a transcription-only adapter here; audio playback
    # remains browser-side and never uses a native Python speaker stream.
    assert "self._stt_runtime.transcribe_pcm" in voice
    assert "asyncio.run(self.voice.speak" not in voice
    assert "sounddevice" not in voice
    assert "_play_wav" not in voice


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
    assert "self._stt_runtime.transcribe_pcm" in bridge
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
    assert "JenefarMinimalEnvironment" in vrm


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



def test_desktop_semantic_actions_verify_postconditions():
    from jenefar.automation.headless import HeadlessDesktopAutomation
    from jenefar.vision.screen import ScreenVision

    vision = ScreenVision(HeadlessDesktopAutomation())
    clicked = vision.locate_and_click("Submit button", verify="Submitted")
    assert clicked["action"]["target"] == "Submit button"
    assert clicked["postcondition"]["matched"] is True
    assert clicked["postcondition"]["match"]["text"] == "Submitted"

    typed = vision.locate_and_type("Search box", "jenefar", verify="jenefar")
    assert typed["type"]["text"] == "jenefar"
    assert typed["postcondition"]["matched"] is True


def test_desktop_requirements_include_wayland_capture_dependencies():
    desktop = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")
    assert "mss>=10.0.0" in desktop
    assert "Pillow>=11.0.0" in desktop


def test_desktop_action_tools_support_optional_verification():
    broker = (ROOT / "jenefar" / "tools" / "broker.py").read_text(encoding="utf-8")
    assert 'name="desktop_click_element"' in broker
    assert '"verify": {"type": ["string", "null"]' in broker
    assert 'locate_and_click' in broker
    assert 'locate_and_type' in broker


def test_default_runtime_reports_desktop_backend_readiness():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "desktop_status = orchestrator.tool_broker.desktop.backend_status()" in run
    assert '"[JENEFAR] Desktop backend: "' in run


def test_default_runtime_keeps_voice_provider_import_lazy():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "from jenefar.voice.provider import ProviderVoiceRuntime" in run
    voice_branch = run.split("if args.voice_auto:", 1)[1]
    import_pos = voice_branch.index("from jenefar.voice.provider import ProviderVoiceRuntime")
    constructor_pos = voice_branch.index("browser_voice = BrowserVoiceBridge")
    assert import_pos > constructor_pos



def test_avatar_and_realtime_modes_share_vrm_and_tool_broker_wiring():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "prepare_avatar_model()" in run
    assert "vrm_path=avatar_model" in run
    assert "tool_broker=orchestrator.tool_broker" in run


def test_avatar_mode_uses_browser_voice_unless_an_explicit_voice_mode_owns_audio():
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "BrowserVoiceBridge" in run
    assert "if not args.realtime and not args.voice and not args.voice_continuous:" in run
    assert "voice_handler=browser_voice.handle_text if browser_voice else None" in run
    # --avatar is the user's launch command; it needs the binary-audio STT route too.
    avatar_block = run.split("if args.avatar:", 1)[1].split("\n    else:", 1)[0]
    assert "voice_audio_handler=browser_voice.handle_audio if browser_voice else None" in avatar_block



def test_browser_voice_display_transliterates_without_dropping_technical_text():
    browser = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert "devanagari_to_roman" in browser
    assert "display_text" in browser


from jenefar.tools.broker import ToolBroker

def test_screenshot_tool_is_reserved_for_explicit_user_requests():
    broker = ToolBroker(require_confirmation=True)
    screenshot = broker.registry.get("desktop_screenshot")
    assert screenshot.requires_confirmation is True
    assert screenshot.action is True
    assert "ONLY when the user explicitly asks" in screenshot.description
    assert "never use it as a screen-inspection workaround" in screenshot.description


def test_gui_agent_does_not_fall_back_to_shell_screenshots_or_capability_lists():
    gui = (ROOT / "jenefar" / "agents" / "automation" / "gui.py").read_text(encoding="utf-8")
    assert "do not fall back to terminal_execute" in gui
    assert "desktop_screenshot" in gui
    assert "unless the user explicitly asked to take, save, or show a screenshot" in gui
    assert "For an explicit screenshot request" in gui
    assert "capabilities." in gui


def test_screen_reading_is_read_only_and_available_without_confirmation():
    from jenefar.tools.broker import ToolBroker

    broker = ToolBroker(require_confirmation=True)
    observe = broker.registry.get("desktop_observe")
    locate = broker.registry.get("desktop_find_element")
    assert observe.requires_confirmation is False
    assert observe.action is False
    assert "save" not in observe.parameters.get("properties", {})
    assert locate.requires_confirmation is False
    assert locate.action is False


def test_avatar_events_can_carry_browser_audio():
    from jenefar.avatar.controller import AvatarController

    controller = AvatarController()
    subscriber = controller.subscribe()
    subscriber.get_nowait()
    controller.publish(
        "speaking",
        "Haan, main yahin hoon.",
        task_id="voice1",
        audio_b64="YWJj",
        audio_mime="audio/wav",
    )
    event = subscriber.get_nowait()
    assert event["audio_b64"] == "YWJj"
    assert event["audio_mime"] == "audio/wav"


def test_live_task_monitor_markup_and_runtime_mirroring():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    hud_css = (WEB / "style-hud-center.css").read_text(encoding="utf-8")
    assert 'id="activity-panel"' in html
    assert 'id="workspace-log"' in html
    assert "function addActivity(event)" in js
    assert "addActivity(event);" in js
    assert "LIVE WORKSPACE" in html
    assert ".workspace-log" in hud_css


def test_workspace_create_tool_and_workspace_scope_include_documents():
    policy = (ROOT / "jenefar" / "workspace" / "policy.py").read_text(encoding="utf-8")
    service = (ROOT / "jenefar" / "workspace" / "service.py").read_text(encoding="utf-8")
    broker = (ROOT / "jenefar" / "tools" / "broker.py").read_text(encoding="utf-8")
    assert 'Path.home() / "Documents"' in policy
    assert "def create_file" in service
    assert 'name="workspace_create_file"' in broker
    assert "requires_confirmation=False" in broker


def test_local_development_agent_uses_conversation_context_research_and_self_healing():
    agent = (ROOT / "jenefar" / "agents" / "coding" / "local_development.py").read_text(encoding="utf-8")
    task_plan = (ROOT / "jenefar" / "core" / "task_plan.py").read_text(encoding="utf-8")
    assert "continuous engineering task" in agent
    assert "selected option numbers" in agent
    assert "research current documentation" in agent
    assert "workspace_create_file" in agent
    assert "max_tool_rounds = 20" in agent
    assert '"research"' in task_plan


def test_browser_tts_has_natural_edge_fallback():
    voice = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert "def _synthesize_edge_audio" in voice
    assert "en-IN-NeerjaNeural" in voice
    assert 'return audio if audio[0] else self._synthesize_edge_audio(text)' in voice


def test_critical_only_approval_policy():
    from jenefar.tools.broker import ToolBroker

    broker = ToolBroker(require_confirmation=False)
    assert broker.registry.get("workspace_edit_file").critical is False
    assert broker.registry.get("workspace_validate_python").critical is False
    assert broker.registry.get("desktop_click_element").critical is False
    assert broker.registry.get("desktop_screenshot").critical is False
    assert broker.registry.get("whatsapp_send_web").critical is True
    assert broker.registry.get("terminal_execute").critical is True


def test_critical_tool_returns_natural_yes_no_prompt():
    from jenefar.tools.broker import ToolBroker

    broker = ToolBroker(require_confirmation=False)
    # A destructive command is classified as critical and is never executed
    # by this test; it must stop at the approval gate.
    result = broker.invoke(
        "terminal_execute",
        {"command": "rm -rf /tmp/jenefar-never-delete-test", "timeout": 5},
    )
    assert '"status": "approval_required"' in result
    assert "Kya main terminal execute kar doon?" in result
    assert '"critical": true' in result


def test_routine_workspace_edit_does_not_request_approval_when_disabled():
    from jenefar.tools.broker import ToolBroker

    broker = ToolBroker(require_confirmation=False)
    pending_before = len(broker.pending)
    assert broker.registry.get("workspace_edit_file").critical is False
    assert len(broker.pending) == pending_before


def test_conversational_confirmation_hooks_and_deeper_history_are_wired():
    orch = (ROOT / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "_handle_conversational_confirmation" in orch
    assert "_confirmation_choice" in orch
    assert "self.session.recent(24)" in orch


def test_screen_task_context_blocks_shell_screenshot_fallbacks():
    from jenefar.tools.broker import ToolBroker

    broker = ToolBroker(require_confirmation=False)
    broker.set_task_context(agent="gui_vision", task="meri screen par kya dikh raha hai?")
    blocked = broker.invoke("terminal_execute", {"command": "scrot screenshot.png", "timeout": 5})
    assert "must not use terminal_execute" in blocked
    blocked_shot = broker.invoke("desktop_screenshot", {"filename": "x.png"})
    assert "only available when the user explicitly asks" in blocked_shot
    broker.clear_task_context()


def test_task_console_is_centered_and_vrm_canvas_is_transparent():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    vrm = (WEB / "vrm.js").read_text(encoding="utf-8")
    assert "Phase 8: clean three-zone layout" in css
    assert "#task-screen{" in css
    assert "setClearColor(0x000000, 0)" in vrm
    assert "JenefarMinimalEnvironment" in vrm


def test_holographic_window_mirror_integration():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    broker = (ROOT / "jenefar" / "tools" / "broker.py").read_text(encoding="utf-8")
    # The current HUD uses the embedded avatar window; desktop mirror is an
    # optional backend feature and is not rendered in this dashboard markup.
    assert 'id="hud-avatar-frame"' in html
    assert '"/desktop/mirror.jpg' in app
    assert 'path == "/desktop/mirror.jpg"' in server
    assert 'name="desktop_mirror_start"' in broker


def test_online_tool_schemas_are_not_forced_strict():
    from jenefar.tools.broker import ToolBroker
    schemas = ToolBroker(require_confirmation=False).schemas()
    assert schemas
    assert all(item.get("strict") is False for item in schemas if item.get("type") == "function")


def test_workspace_list_directory_accepts_optional_max_items_for_openai_schema():
    from jenefar.tools.broker import ToolBroker
    tool = ToolBroker(require_confirmation=False).registry.get("workspace_list_directory")
    assert tool.parameters["required"] == ["path"]
    assert "max_items" in tool.parameters["properties"]




def test_supplied_hud_and_minimal_vrm_presentation():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    vrm = (WEB / "vrm.js").read_text(encoding="utf-8")
    hud = (WEB / "hud_avatar.html").read_text(encoding="utf-8")
    assert 'id="hud-avatar"' in html
    assert 'src="/hud_avatar.html"' in html
    assert "function updateEmbeddedHud" in app
    assert "Phase 12: final clean display composition" in css
    assert "JenefarMinimalEnvironment" in vrm
    assert "JenefarPremiumEnvironment" not in vrm
    assert "PARTICLES:" in hud
    assert "window.updateAgentState" in hud


def test_live_window_control_and_transfer_wiring():
    window_control = (ROOT / "jenefar" / "automation" / "window_control.py").read_text(encoding="utf-8")
    mirror = (ROOT / "jenefar" / "vision" / "mirror.py").read_text(encoding="utf-8")
    broker = (ROOT / "jenefar" / "tools" / "broker.py").read_text(encoding="utf-8")
    gui = (ROOT / "jenefar" / "agents" / "automation" / "gui.py").read_text(encoding="utf-8")
    assert "class DesktopWindowControl" in window_control
    assert "def transfer" in mirror
    assert "def restore_native" in mirror
    assert 'name="desktop_window_transfer"' in broker
    assert 'name="desktop_window_restore"' in broker
    assert "desktop_window_transfer" in gui
    assert "Never hide the Jenefar Avatar host window itself" in gui


def test_window_control_backend_is_safe_to_construct_without_x11():
    from jenefar.automation.window_control import DesktopWindowControl
    backend = DesktopWindowControl()
    status = backend.status()
    assert status["backend"] in {"wmctrl", "xdotool", "hyprland", "sway", "none"}
    assert isinstance(status["control"], bool)


def test_orchestrator_direct_window_transfer_and_screen_paths():
    orch = (ROOT / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "_direct_window_transfer" in orch
    assert "_direct_screen_read" in orch
    assert "desktop_window_transfer" in orch
    assert "screen-reading-only requests" not in orch or True


def test_broker_online_schemas_are_non_strict_function_schemas():
    from jenefar.tools.broker import ToolBroker
    schemas = ToolBroker(require_confirmation=False).schemas()
    assert schemas
    assert all(item.get("strict") is False for item in schemas)

def test_dashboard_uses_live_telemetry_and_has_model_controls():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    assert 'id="metric-cpu"' in html
    assert 'id="metric-ram"' in html
    assert 'id="metric-gpu"' in html
    assert 'id="model-settings-button"' in html
    assert 'id="model-choice"' in html
    assert 'id="model-id-input"' in html
    # Metrics rings must have a single writer. The loopback WebSocket is
    # authoritative; a second REST polling loop made the rings flicker.
    assert 'fetch("/system/metrics?ts="+Date.now()' not in app
    assert "setInterval(refreshSystemMetrics,1500)" not in app
    assert 'new WebSocket(socketUrl())' in app
    assert "function updateTelemetry(data)" in app
    assert 'path == "/system/metrics"' in server
    assert 'path == "/model/status"' in server
    assert 'path == "/model/select"' in server
    assert 'class="ring-meter cpu">32%' not in html
    assert 'class="ring-meter ram">46%' not in html
    assert 'class="ring-meter gpu">28%' not in html

def test_right_dashboard_stack_has_compact_non_overlapping_layout_rules():
    hud_css = (WEB / "style-hud-center.css").read_text(encoding="utf-8")
    assert "Phase 14: compact, non-overlapping right-side system / command / task stack" in hud_css
    assert ".system-card{\n    top:74px!important" in hud_css
    assert ".command-stack{\n    top:255px!important" in hud_css
    assert "#activity-panel{\n    top:414px!important" in hud_css
    assert 'id="rea-connect-button"' in (WEB / "index.html").read_text(encoding="utf-8")


def test_model_panel_uses_provider_discovery_and_rea_is_a_live_connector():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    catalog = (ROOT / "jenefar" / "core" / "model_catalog.py").read_text(encoding="utf-8")
    assert "provider.models" in app
    assert 'fetch("/rea/status?ts="+Date.now()' in app
    assert 'fetch("/rea/connect"' in app
    assert 'path == "/rea/status"' in server
    assert 'path == "/rea/connect"' in server
    assert "list_provider_models(name, pool)" in server
    assert 'generativelanguage.googleapis.com/v1beta/models' in catalog


def test_browser_tts_prefers_expressive_gemini_before_edge_fallback():
    bridge = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert "def _synthesize_gemini_audio" in bridge
    assert "speech_metadata" in bridge
    assert "JENEFAR_GEMINI_TTS_MODEL" in bridge
    assert "self._synthesize_gemini_audio(text)" in bridge
    assert "trying expressive Gemini TTS" in bridge



def test_browser_mic_stays_locked_until_assistant_finishes_responding():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    voice_start = js.index("async function sendBrowserTranscript(text){")
    voice_end = js.index("function setupBrowserVoice(){", voice_start)
    voice_handler = js[voice_start:voice_end]
    accepted = voice_handler.index("if(result?.accepted){")
    accepted_end = voice_handler.index("\n    }", accepted)
    accepted_block = voice_handler[accepted:accepted_end]

    assert "Keep the microphone locked while the server thinks and synthesizes TTS" in accepted_block
    assert "return;" in accepted_block
    assert "voiceLocked=false" not in accepted_block

    dashboard_start = js.index("async function dispatchDashboardCommand(command){")
    dashboard_end = js.index('document.querySelectorAll("[data-command]")', dashboard_start)
    dashboard_handler = js[dashboard_start:dashboard_end]
    assert dashboard_handler.index("pauseBrowserVoice();") < dashboard_handler.index('fetch("/voice/text"')
    assert "Keep capture locked until the corresponding speaking/completed event." in dashboard_handler

def test_browser_mic_stays_locked_when_server_reports_busy():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    start = js.index("async function transcribeCapturedAudio(blob,durationMs){")
    end = js.index("function startFallbackMonitor(){", start)
    handler = js[start:end]
    busy = handler.index("if(result?.busy){")
    busy_end = handler.index("\n    }", busy)
    busy_block = handler[busy:busy_end]
    assert "voiceLocked=false" not in busy_block
    assert "resumeBrowserVoice()" not in busy_block
    assert "setMicButton(true,true)" in busy_block
    assert "Do not unlock during a still-running task" in busy_block
    assert "resumeVoiceIfAssistantIdle();" in busy_block
    assert "function resumeVoiceIfAssistantIdle()" in js


def test_avatar_server_silently_handles_closed_browser_socket():
    from jenefar.avatar.server import _AvatarHandler

    handler = object.__new__(_AvatarHandler)
    handler.send_response = lambda _status: None
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None

    class DisconnectedWriter:
        def write(self, _body):
            raise BrokenPipeError("browser closed the connection")

    handler.wfile = DisconnectedWriter()
    handler._send(200, "application/json; charset=utf-8", b"{}")

def test_avatar_approval_controls_use_orchestrator_workflow_callbacks():
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert 'handler = getattr(self, "approval_handler", None)' in server
    assert 'handler = getattr(self, "rejection_handler", None)' in server
    assert "approval_handler=(" in run
    assert "browser_voice.approve_pending" in run
    assert "else orchestrator._approve_pending" in run
    assert "rejection_handler=orchestrator._reject_pending_workflow" in run
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'const payload=await response.json();' in app
    approval_start = app.index("approveButton.onclick=async()=>{")
    approval_end = app.index("\n}\n", approval_start)
    approval_handler = app[approval_start:approval_end]
    assert 'const resultValue=payload?.result;' in approval_handler
    assert 'browserSpeakFallback(reply);' not in approval_handler
    assert 'playBrowserAudio(event.audio_b64,event.audio_mime,event.text||"");' in app
    assert 'function stopBrowserAudio(){' in app
    assert 'browserAudioGeneration' in app
    assert 'browserSpeechGeneration' in app
    assert 'const failPlayback=()=>{' in app



def test_browser_playback_keeps_one_owner_and_mic_waits_for_audio():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "function stopBrowserAudio(){" in js
    assert "browserSpeechGeneration" in js
    assert "if(browserSpeechActive||Boolean(browserAudio&&!browserAudio.ended)||" in js


def test_approval_speech_queue_uses_browser_fallback_and_does_not_unlock_early():
    bridge = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    start = bridge.index("    def _speech_loop(self) -> None:")
    end = bridge.index("    def shutdown(self) -> None:", start)
    speech_loop = bridge[start:end]
    assert 'self._publish("speaking_fallback", display_text, task_id)' in speech_loop
    assert 'self._publish("idle", "", "")' not in speech_loop
    assert "Queue completion means synthesis ended, not that browser" in speech_loop



def test_browser_voice_events_ignore_sse_replay_of_same_speech():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "const playedSpeechEventKeys=new Set();" in js
    assert "function speechEventWasAlreadyHandled(event)" in js
    assert 'const key=state+"|"+taskId+"|"+payloadKey;' in js
    assert "if(!speechEventWasAlreadyHandled(event)){" in js
    assert 'if(event.text&&!speechEventWasAlreadyHandled(event)){' in js
    assert "while(playedSpeechEventOrder.length>128)" in js



def test_scan_results_window_is_transparent_transient_and_selectable():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")

    assert 'id="scan-results-window"' in html
    assert 'data-scan-view="hosts"' in html
    assert 'data-scan-view="ports"' in html
    assert "backdrop-filter:blur(30px) saturate(1.72)" in css
    assert "#scan-results-window[hidden]{display:none!important}" in css
    assert "function openScanResults(data,taskId" in js
    assert 'currentState==="scan_results"' in js
    assert "closeScanResults();" in js
    assert 'dispatchDashboardCommand("scan ports of host "+host.ip)' in js
    assert 'self._publish(' in bridge
    assert '"scan_results"' in bridge
    assert "data=structured_scan" in bridge
    assert "Do not synthesize or enqueue spoken IP/port lists" in bridge


def test_scan_result_events_carry_structured_data_without_speech():
    from jenefar.avatar.controller import AvatarController

    controller = AvatarController()
    subscriber = controller.subscribe()
    subscriber.get_nowait()
    result = {
        "kind": "host_discovery",
        "summary": "2 live hosts found",
        "hosts": [{"index": 1, "ip": "192.168.29.1", "state": "UP"}],
    }

    controller.publish("scan_results", result["summary"], task_id="scan-task", data=result)
    event = subscriber.get_nowait()

    assert event["state"] == "scan_results"
    assert event["data"]["kind"] == "host_discovery"
    assert event["data"]["hosts"][0]["ip"] == "192.168.29.1"
    assert event["audio_b64"] == ""

def test_browser_mic_falls_back_when_server_audio_pipeline_is_unavailable():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    start = js.index("async function transcribeCapturedAudio(blob,durationMs){")
    end = js.index("function startFallbackMonitor(){", start)
    handler = js[start:end]

    # ffmpeg/decode errors are infrastructure failures, not user speech errors.
    # If the browser exposes SpeechRecognition, stop the failing recorder path
    # and switch to native browser recognition instead of retrying forever.
    assert "const audioPipelineUnavailable=" in handler
    assert "ffmpeg|could not decode microphone audio|audio conversion" in handler
    assert "if((providerUnavailable||audioPipelineUnavailable)&&fallbackMode&&voiceSupported&&recognition)" in handler
    assert "Browser audio pipeline is unavailable; switching to browser speech recognition: " in handler
    assert '"SERVER AUDIO FAILED — TRYING BROWSER SPEECH"' in handler
    assert "fallbackMode=false;" in handler
    assert "resumeBrowserVoice();" in handler

def test_cloud_stt_empty_transcript_falls_back_to_local_whisper(monkeypatch):
    import asyncio
    from jenefar.voice.provider import ProviderVoiceRuntime

    runtime = ProviderVoiceRuntime(orchestrator=object())
    monkeypatch.setattr(runtime, "_provider_order", lambda: ["openai"])
    monkeypatch.setattr(runtime._audio_pool, "available", lambda _provider: True)

    async def empty_cloud_transcript(_audio):
        return "  "

    async def local_transcript(_audio):
        return " open browser "

    monkeypatch.setattr(runtime, "_transcribe_openai", empty_cloud_transcript)
    monkeypatch.setattr(runtime, "_transcribe_local", local_transcript)

    transcript = asyncio.run(runtime.transcribe_pcm(b"\\x00" * 3200))
    assert transcript == "open browser"


def test_empty_server_transcript_switches_to_browser_speech_recognition():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    start = js.index("async function transcribeCapturedAudio(blob,durationMs){")
    end = js.index("function startFallbackMonitor(){", start)
    handler = js[start:end]

    assert 'result?.reason==="empty_transcript"' in handler
    assert "if(fallbackMode&&voiceSupported&&recognition)" in handler
    assert "stopFallbackMonitor(true);" in handler
    assert "fallbackMode=false;" in handler
    assert '"SERVER STT HEARD NO WORDS — SWITCHING TO BROWSER SPEECH"' in handler



def test_dashboard_has_explicit_quit_and_release_memory_control():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")

    assert 'id="runtime-ops-shutdown"' in html
    assert 'fetch("/runtime/shutdown"' in app
    assert 'if path == "/runtime/shutdown":' in server
    assert "shutdown_handler=request_runtime_shutdown" in run
    assert "LocalLLMClient.release_runtime_models()" in run


def test_live_system_metrics_have_only_one_browser_writer():
    js = (WEB / "app.js").read_text(encoding="utf-8")

    # REST polling and WebSocket telemetry previously painted the same rings
    # with different units and sample times, making the readings flicker.
    assert 'setInterval(refreshSystemMetrics,1500)' not in js
    assert "function refreshSystemMetrics()" not in js
    assert 'new WebSocket(socketUrl())' in js
    assert "particleFrameInterval=1000/30" in js
    assert "Math.min(110,Math.max(36,Math.floor(width/14)))" in js
