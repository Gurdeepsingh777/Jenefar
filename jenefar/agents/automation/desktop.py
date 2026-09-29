from jenefar.agents.llm_agent import BaseLLMAgent


class AutomationAgent(BaseLLMAgent):
    name = "automation"
    description = "Approval-gated desktop automation specialist"
    use_tools = True
    allow_action_tools = True
    system_prompt = """You are Jenefar's desktop automation specialist.
Use only the provided desktop primitives. Treat screen coordinates and typing
as user-authorized actions that require explicit confirmation. Prefer screenshots
and read-only screen information before acting. Never claim an action succeeded
unless the tool result confirms it."""
    keywords = (
        "desktop", "screen", "screenshot", "mouse", "keyboard",
        "click", "type", "press", "gui", "window",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)
