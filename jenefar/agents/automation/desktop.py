from jenefar.agents.llm_agent import BaseLLMAgent


class AutomationAgent(BaseLLMAgent):
    name = "automation"
    description = "Approval-gated desktop automation specialist"
    use_tools = True
    allow_action_tools = True
    system_prompt = """You are Jenefar's desktop automation specialist.
Use the provided semantic screen, desktop, browser and local-media tools.
Prefer vision-backed semantic element lookup over guessed coordinates. Treat desktop
typing/clicking, semantic GUI actions and microphone song recognition as confirmation-gated.
Browser playback and local media playback are low-risk user-requested actions.
Prefer tool results and never claim an action succeeded unless the result confirms it."""
    keywords = (
        "desktop", "screen", "screenshot", "mouse", "keyboard",
        "click", "type", "press", "gui", "window",
        "browser", "youtube", "song", "mp3", "vlc", "play", "music",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)
