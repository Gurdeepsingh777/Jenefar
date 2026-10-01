from jenefar.agents.llm_agent import BaseLLMAgent


class VisionGUIAgent(BaseLLMAgent):
    name = "gui_vision"
    description = "Vision-backed semantic desktop control specialist"
    use_tools = True
    allow_action_tools = True
    model_role = "vision"
    max_tool_rounds = 12
    system_prompt = """You are Jenefar's vision-backed GUI specialist.
First check desktop_backend_status. If pyautogui is unavailable, report the focused install command and stop. When performing clicks or typing, use the optional verify postcondition for visible expected results and use the returned verification state before claiming success. When ready, use semantic screen understanding instead of guessed coordinates whenever possible.
First observe or locate the requested UI element. For clicks or typing, use the
semantic action tools so the current screenshot is analyzed immediately before the
action. After every action, observe the screen again when verification matters.
Do not claim a GUI action succeeded unless the tool result confirms it.
For a request that asks what is currently visible on screen, use desktop_observe first.
For an explicit screenshot request, use desktop_screenshot only when the user asks to take,
save, or show a screenshot. For screen reading/inspection, desktop_observe is the only
screen-understanding path.
If desktop_observe fails, report the verified failure and stop; do not fall back to terminal_execute,
ImageGrab, gnome-screenshot, scrot, desktop_screenshot, or any other screenshot workaround
unless the user explicitly asked to take, save, or show a screenshot. Never invent visible
controls, coordinates, screenshots, or capabilities."""
    keywords = (
        "screen", "screenshot", "find on screen", "locate on screen",
        "click the", "click on", "press the button", "find the button",
        "open the app", "open application", "gui", "interface",
        "search box", "address bar", "button", "menu", "tab",
        "semantic click", "semantic gui", "what is on my screen",
        "screen par", "screen pe", "screen kya", "screen read",
        "live screen", "meri screen", "mere screen", "screen dekho",
        "screen dikh", "screen me kya",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)
