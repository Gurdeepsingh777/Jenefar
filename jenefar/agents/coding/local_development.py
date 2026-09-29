from jenefar.agents.llm_agent import BaseLLMAgent


class LocalDevelopmentAgent(BaseLLMAgent):
    name = "local_development"
    description = "Authorized local-file inspection, Python execution and code editing specialist"
    use_tools = True
    allow_action_tools = True
    system_prompt = """You are Jenefar's local development specialist.
Work only inside the authorized local workspace roots. Inspect files before modifying
them. When the user asks to run a Python script, use workspace_run_python. When the
user asks to fix or add a feature, inspect the current file, make the smallest correct
edit with workspace_edit_file, then run the script/tests and report the result.
Never claim a change or execution succeeded unless the tool result confirms it.
Do not execute arbitrary shell commands to bypass workspace policy."""
    keywords = (
        ".py", "python file", "python script", "script", "file", "folder",
        "directory", "fix error", "fix the error", "modify", "edit",
        "update this file", "change this file", "add a feature", "custom feature",
        "run it", "execute it", "check this file", "check the file",
        "message-sending", "video calling", "video call",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)
