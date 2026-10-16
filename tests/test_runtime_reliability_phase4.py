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
