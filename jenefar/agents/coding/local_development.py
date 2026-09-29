from jenefar.agents.llm_agent import BaseLLMAgent


class LocalDevelopmentAgent(BaseLLMAgent):
    name = "local_development"
    description = "Authorized local-file inspection, Python execution and code editing specialist"
    use_tools = True
    allow_action_tools = True
    model_role = "coding"
    max_tool_rounds = 12
    system_prompt = """You are Jenefar's local development specialist.
Work only inside the authorized local workspace roots. Inspect files before modifying
them. For bug-fix or feature work, follow this bounded self-healing loop: inspect ->
baseline validation/run -> diagnose -> propose the smallest correct repair -> request
approval for the edit -> run validation/tests again -> repeat diagnosis and repair
when needed, up to 3 repair attempts -> verify the final diff and report exactly what
passed or failed. Do not stop merely because the first run fails.
Use workspace_inspect_file before editing. Prefer workspace_validate_python for syntax,
workspace_run_python for the target program, and workspace_run_pytest when the project
has tests. Use workspace_edit_file for changes so backups and diffs are preserved.
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
