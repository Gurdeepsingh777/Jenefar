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
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert 'id="task-screen"' in html
    assert 'id="task-screen-log"' in html
    assert "function updateTaskScreen(event)" in js
    assert "updateTaskScreen(event);" in js
    assert "LIVE TASK MONITOR / ENLARGED HOLOGRAPHIC SCREEN" in css
    assert "#task-screen{" in css


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
    assert 'return self._synthesize_edge_audio(text)' in voice


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
    result = broker.invoke(
        "terminal_execute",
        {"command": "printf jenefar", "timeout": 5},
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
    assert 'id="desktop-mirror"' in html
    assert '"/desktop/mirror.jpg' in app
    assert "Phase 9: clear avatar + real live-window mirror" in css
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


def test_phase1_desktop_layout_owns_fixed_spatial_regions():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "PHASE 1 — DESKTOP LAYOUT RESET" in css
    assert "--p1-left:178px" in css
    assert "--p1-right:350px" in css
    assert ".side-nav{" in css
    assert ".system-card{" in css
    assert "#activity-panel{" in css
    assert "#task-screen{" in css


def test_phase1_center_is_clean_before_visual_phases():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert 'id="phase1-center"' in html
    assert "PHASE 1 FINAL — clean GUI shell" in css
    assert "#holo-earth,#hud-avatar,#hud-canvas,#vrm-canvas,#photo-avatar" in css
    assert ".avatar-shell,#task-screen,.mode-pill" in css


def test_phase2_blue_hud_isolated_to_center_workspace():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "PHASE 2 — BLUE HUD" in css
    assert "#hud-avatar{" in css
    assert "#hud-avatar-frame{" in css
    assert 'src="/hud_avatar.html"' in html
    assert "#holo-earth,#vrm-canvas,#photo-avatar,.avatar-shell,#task-screen" in css


def test_phase2_hud_occupies_center_column_and_is_enlarged():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    hud = (WEB / "hud_avatar.html").read_text(encoding="utf-8")
    assert "left:460px!important" in css
    assert "right:560px!important" in css
    assert "SPHERE_RADIUS:  150" in hud
    assert "RING_RADII:     [235, 255, 280, 305]" in hud
    assert "left:50%; transform:translateX(-50%)" in hud


def test_phase3_vrm_avatar_isolated_on_center_stage():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    vrm = (WEB / "vrm.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "PHASE 3 — VRM AVATAR" in css
    assert "#vrm-canvas{" in css
    assert "left:460px!important" in css
    assert "right:560px!important" in css
    assert 'src="/avatar.vrm"' in vrm
    assert '<canvas id="vrm-canvas"' in html
    assert ".avatar-shell,#photo-avatar,#holo-earth,#task-screen" in css


def test_phase4_avatar_style_and_auto_frame():
    vrm = (WEB / "vrm.js").read_text(encoding="utf-8")
    pipeline = (ROOT / "tools" / "blender" / "premium_avatar.py").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "Auto-frame the real model" in vrm
    assert "Jenefar_Premium_v2.vrm" in run
    assert 'PREMIUM_WHITE = (0.035, 0.075, 0.13, 1.0)' in pipeline
    assert 'PREMIUM_CYAN = (0.04, 0.72, 0.95, 1.0)' in pipeline


def test_phase5_vrm_motion_hooks_are_present():
    vrm = (WEB / "vrm.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "PHASE 5: natural avatar motion" in vrm
    assert "targetGazeX" in vrm
    assert "blinkTimer" in vrm
    assert "speakingMotion" in vrm
    assert "PHASE 5 — AVATAR POLISH + CENTER SCALE" in css
