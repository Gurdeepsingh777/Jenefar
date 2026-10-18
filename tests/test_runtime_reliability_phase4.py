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
    assert 'if(captionEl) captionEl.textContent=isRawScannerActivity' in js
    assert '"Network scan running"' in js
    assert 'String(event.data?.summary||event.text||caption)' in js
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

def test_task_matched_skills_are_added_to_agent_instructions():
    from jenefar.agents.llm_agent import BaseLLMAgent
    from jenefar.core.agent import AgentContext

    class CaptureLLM:
        def complete(self, prompt, **kwargs):
            self.instructions = kwargs["instructions"]
            return type("Response", (), {
                "text": "Done",
                "provider": "test",
                "response_id": "test",
                "pending_tools": [],
                "model": "test",
                "model_role": "test",
            })()

    agent = BaseLLMAgent.__new__(BaseLLMAgent)
    agent.system_prompt = "Test agent."
    agent.model_role = "test"
    agent.use_web_search = False
    agent.use_tools = False
    agent.allow_action_tools = False
    agent.max_tool_rounds = 1
    agent.tool_broker = None
    agent.llm = CaptureLLM()
    ctx = AgentContext(
        task="Create a blender render",
        metadata={
            "skills": [{
                "name": "blender",
                "description": "Blender helper",
                "keywords": ["blender", "render"],
                "system_prompt": "Prefer cycles render engine.",
            }],
            "response_language": "English",
        },
    )
    agent.run(ctx)
    assert "Task-matched skill guidance" in agent.llm.instructions
    assert "Prefer cycles render engine." in agent.llm.instructions


def test_mediarecorder_fallback_is_connected_to_provider_stt():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    voice = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "new MediaRecorder(fallbackStream" in app
    assert 'fetch("/voice/audio"' in app
    assert 'if path == "/voice/audio":' in server
    assert "def handle_audio(self, audio: bytes" in voice
    assert "self._stt_runtime.transcribe_pcm" in voice
    assert "voice_audio_handler=browser_voice.handle_audio" in run


def test_browser_hud_does_not_draw_an_opaque_horizon_plate():
    hud = (WEB / "hud_avatar.html").read_text(encoding="utf-8")
    assert "ctx.fillRect(0, horizonY - 40, W, 48)" not in hud
    assert "#vignette { display:none!important" in hud
    assert "#top-telemetry, #caption-box {" in hud
    assert "background:transparent!important;" in hud


def test_terminal_safe_local_commands_auto_run_but_destructive_commands_wait():
    import json
    from jenefar.tools.broker import ToolBroker

    broker = ToolBroker(require_confirmation=False)
    safe = json.loads(broker.invoke("terminal_execute", {"command": "printf jenefar", "timeout": 5}))
    assert safe["status"] == "ok"
    assert "jenefar" in safe["result"]

    dangerous = json.loads(broker.invoke(
        "terminal_execute",
        {"command": "rm -rf /tmp/jenefar-never-delete-test", "timeout": 5},
    ))
    assert dangerous["status"] == "approval_required"
    assert dangerous["critical"] is True

    background = json.loads(broker.invoke(
        "terminal_execute",
        {"command": "printf harmless & rm -rf /tmp/jenefar-never-delete-test", "timeout": 5},
    ))
    assert background["status"] == "approval_required"
    assert background["critical"] is True


def test_confirmation_mode_defaults_to_critical_only(monkeypatch):
    from jenefar.core.config import load_config

    monkeypatch.setenv("JENEFAR_REQUIRE_CONFIRMATION", "true")
    monkeypatch.delenv("JENEFAR_CONFIRMATION_MODE", raising=False)
    assert load_config().require_confirmation_for_tools is False
    monkeypatch.setenv("JENEFAR_CONFIRMATION_MODE", "all")
    assert load_config().require_confirmation_for_tools is True



def test_realtime_voice_mode_is_connected_and_uses_conversational_instructions():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "realtime.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "realtime" / "server.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'id="realtime-button"' in html
    assert 'id="realtime-state"' in html
    assert '<script src="/realtime.js"></script>' in html
    assert "new RTCPeerConnection()" in js
    assert "function parseToolResult(payload)" in js
    assert "LIVE VOICE FAILED" in js
    assert "female-presenting conversational assistant" in server
    assert "Do not ask for approval unless the tool broker returns approval_required." in server
    assert "active OpenAI API access and credits" in env


def test_successful_multi_tool_workflow_is_saved_as_procedure_and_skill(tmp_path: Path):
    from jenefar.core.orchestrator import JenefarOrchestrator
    from jenefar.skills.manager import SkillManager

    class CaptureMemory:
        def __init__(self):
            self.saved = []

        def save_procedure(self, **kwargs):
            self.saved.append(kwargs)

    root = tmp_path / "skills"
    orchestrator = JenefarOrchestrator.__new__(JenefarOrchestrator)
    orchestrator.skills = SkillManager(tmp_path / "skill-state.json", skill_roots=[root])
    orchestrator.memory_engine = CaptureMemory()

    orchestrator._auto_learn_successful_workflow(
        "Check Python project tests and summarize the results",
        "local_development",
        [{"tool": "workspace_list_files"}, {"tool": "workspace_run_tests"}],
    )

    assert len(orchestrator.memory_engine.saved) == 1
    assert orchestrator.memory_engine.saved[0]["source"] == "auto_verified_workflow"
    learned = [item for item in orchestrator.skills.list() if item["name"].startswith("learned_")]
    assert learned
    assert all(item["enabled"] for item in learned)
    learned_file = next(root.glob("*/SKILL.md"))
    body = learned_file.read_text(encoding="utf-8")
    assert "workspace_list_files" in body
    assert "workspace_run_tests" in body


def test_automatic_skill_learning_skips_sensitive_and_security_workflows(tmp_path: Path):
    from jenefar.core.orchestrator import JenefarOrchestrator
    from jenefar.skills.manager import SkillManager

    class CaptureMemory:
        def __init__(self):
            self.saved = []

        def save_procedure(self, **kwargs):
            self.saved.append(kwargs)

    root = tmp_path / "skills"
    orchestrator = JenefarOrchestrator.__new__(JenefarOrchestrator)
    orchestrator.skills = SkillManager(tmp_path / "skill-state.json", skill_roots=[root])
    orchestrator.memory_engine = CaptureMemory()
    actions = [{"tool": "workspace_list_files"}, {"tool": "workspace_run_tests"}]

    orchestrator._auto_learn_successful_workflow(
        "Check my API key and password",
        "local_development",
        actions,
    )
    orchestrator._auto_learn_successful_workflow(
        "Review a local security workflow",
        "cybersecurity",
        actions,
    )

    assert orchestrator.memory_engine.saved == []
    assert not list(root.glob("*/SKILL.md"))



def test_realtime_session_includes_enabled_persistent_skills(monkeypatch):
    import json
    from urllib import request
    from jenefar.realtime.server import create_ephemeral_session

    class FakeSkills:
        def list(self):
            return [{
                "name": "learned_python_tests",
                "description": "Verify a local Python test suite.",
                "keywords": ["python", "pytest"],
                "system_prompt": "Check the current checkout before running tests.",
                "enabled": True,
            }]

    class FakeMemory:
        def find_procedures(self, query, limit=5):
            return [{
                "name": "auto_python_test",
                "source": "auto_verified_workflow",
                "steps": ["Use workspace_list_files", "Use workspace_run_tests"],
                "constraints": ["Re-check current project state"],
            }]

    class FakeBroker:
        skills = FakeSkills()
        memory = FakeMemory()

        def schemas(self, **kwargs):
            return []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"value": "ephemeral-test-secret"}).encode("utf-8")

    captured = {}

    def fake_urlopen(req, timeout=20):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    result = create_ephemeral_session(FakeBroker())

    instructions = captured["payload"]["session"]["instructions"]
    assert result["value"] == "ephemeral-test-secret"
    assert "female-presenting conversational assistant" in instructions
    assert "learned_python_tests" in instructions
    assert "Check the current checkout before running tests." in instructions
    assert "auto_python_test" in instructions
    assert "approval_required" in instructions



def test_structured_scan_results_are_published_and_not_spoken_as_host_lists():
    orchestrator = (ROOT / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")

    assert "approval_handler=(" in run
    assert "browser_voice.approve_pending" in run
    assert orchestrator.index("if self._is_local_host_port_scan_request(text):") < orchestrator.index("direct_window = self._direct_window_transfer(text)")
    assert 'invoke("kali_tool_execute", arguments, confirmed=True)' in orchestrator
    assert "if browser_voice_enabled" in run
    assert "rejection_handler=orchestrator._reject_pending_workflow" in run
    assert 'avatar.publish("scan_results", str(data["summary"]), data=data)' in orchestrator
    assert 'avatar.publish("scan_results", str(result_data["summary"]), data=result_data)' in orchestrator
    assert "only the compact result-window summary to the voice UI." in orchestrator
    assert 'summary += "\\nReported hosts: "' in orchestrator
    assert 'payload["structured_scan"] = scan_data' in server
    assert "openScanResults(payload.structured_scan" in app
    assert "else if(resultValue?.structured_scan)" in app
    assert "Do not duplicate its one-line summary" in app
    assert 'dispatchDashboardCommand("scan ports of host "+host.ip)' in app
    assert "New instruction closes this window automatically" in (WEB / "index.html").read_text(encoding="utf-8")
    assert "if owner is scan_owner" in (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    assert "self.orchestrator._latest_scan_result = None" in (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    assert '"-Pn", "-n", "-sT", "-sV"' in orchestrator
    assert '"filtered_port_count": filtered_count' in orchestrator
    assert '"closed_port_count": closed_count' in orchestrator
    assert '"stdout": stdout' in orchestrator
    assert '"stderr": str(result.get("stderr") or "")' in orchestrator
    assert 'appendExactNmapOutput(scanResultsList,data)' in app
    assert 'scanNode("summary","","EXACT NMAP OUTPUT")' in app
    assert 'scanNode("pre","scan-raw-pre",stdout)' in app
    assert '["PORT","STATE","SERVICE","VERSION / DETAIL"]' in app
    assert "NO SCAN YET" in app
    assert "Host reachability was not confirmed." in app
    assert "No open or filtered TCP ports were reported." in app
    assert 'data?.scan_status==="error"' in app
    assert 'hostStatus==="ERROR"?"SCAN FAILED"' in app
    assert 'scanResultsWindow&&!scanResultsWindow.hidden&&["listening","queued","thinking"].includes(currentState)' in app
    assert "Host discovery did not complete." in app
    assert "REACHABILITY UNKNOWN · " in app
    assert "filtered-only output does not" in orchestrator



def test_network_scope_picker_shows_block_reason_without_false_zero_host_count():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    orchestrator = (ROOT / "jenefar" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    network_info = (ROOT / "jenefar" / "tools" / "network_info.py").read_text(encoding="utf-8")

    assert 'const scanBlocked=data?.scan_status==="blocked";' in app
    assert 'const scanSelectionRequired=data?.scan_status==="selection_required";' in app
    assert "renderNetworkScopePanel(scanResultsList,data)" in app
    assert 'option.authorized===true' in app
    assert 'dispatchDashboardCommand("scan network "+network)' in app
    assert "CURRENT AUTHORIZED TARGETS" in app
    assert "CHANGE NETWORK / INTERFACE" in app
    assert "showNetworkPicker=!showNetworkPicker" in app
    assert "No Nmap command was executed" in orchestrator
    assert '"networks": candidates' in network_info
    assert ".scan-network-option" in css
    assert ".scan-scope-badge.denied" in css



def test_browser_tts_includes_local_piper_before_network_edge_fallback():
    voice = (ROOT / "jenefar" / "voice" / "browser.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")

    assert "def _synthesize_local_piper_audio" in voice
    assert '"--model", str(model_path)' in voice
    assert '"--output_file", output_path' in voice
    assert "JENEFAR_LOCAL_TTS_TIMEOUT_SECONDS" in voice
    browser_tts = voice[voice.index("    def _synthesize_browser_audio"):]
    assert browser_tts.index("self._synthesize_local_piper_audio(text)") < browser_tts.index("self._synthesize_edge_audio(text)")
    assert "JENEFAR_LOCAL_TTS_MODEL=" in env
    assert "configured Piper" in env
    assert "configured local Piper -> Edge" in run


def test_desktop_health_is_actionable_in_doctor_and_dashboard():
    desktop = (ROOT / "jenefar" / "automation" / "desktop.py").read_text(encoding="utf-8")
    headless = (ROOT / "jenefar" / "automation" / "headless.py").read_text(encoding="utf-8")
    server = (ROOT / "jenefar" / "avatar" / "server.py").read_text(encoding="utf-8")
    run = (ROOT / "run.py").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")

    assert '"input_control": False' in desktop
    assert '"desktop_ready": False' in headless
    assert 'if path == "/desktop/status":' in server
    assert 'fetch("/desktop/status?ts="+Date.now()' in app
    assert 'id="service-desktop"' in html
    assert 'id="desktop-status-detail"' in html
    assert 'status["diagnosis"] = diagnosis' in desktop
    assert '"  desktop diagnosis             "' in run
    assert ".desktop-diagnostic[data-state="unavailable"]" in css
