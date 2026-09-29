from jenefar.agents.llm_agent import BaseLLMAgent


class VisionGUIAgent(BaseLLMAgent):
    name = "gui_vision"
    description = "Vision-backed semantic desktop control specialist"
    use_tools = True
    allow_action_tools = True
    model_role = "vision"
    max_tool_rounds = 12
    system_prompt = """You are Jenefar's vision-backed GUI specialist.
Use semantic screen understanding instead of guessed coordinates whenever possible.
First observe or locate the requested UI element. For clicks or typing, use the
semantic action tools so the current screenshot is analyzed immediately before the
action. After every action, observe the screen again when verification matters.
Do not claim a GUI action succeeded unless the tool result confirms it.
Never invent visible controls or coordinates."""
    keywords = (
        "screen", "screenshot", "find on screen", "locate on screen",
        "click the", "click on", "press the button", "find the button",
        "open the app", "open application", "gui", "interface",
        "search box", "address bar", "button", "menu", "tab",
        "semantic click", "semantic gui", "what is on my screen",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)
