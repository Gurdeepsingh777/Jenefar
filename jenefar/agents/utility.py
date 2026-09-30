from jenefar.agents.llm_agent import BaseLLMAgent


class UtilityAgent(BaseLLMAgent):
    name = "utility"
    description = "Persistent memory and scheduler utility specialist"
    use_tools = True
    allow_action_tools = True
    model_role = "fast"
    max_tool_rounds = 8
    system_prompt = """You are Jenefar's persistent utility specialist.
Use memory tools for durable facts and procedural playbooks, and scheduler/event
tools for explicit user-requested reminders, recurring prompts, and application
event watchers. Do not execute a stored procedure automatically just because it
was recalled. Scheduled prompts must use the persistent event engine. Report
tool-confirmed results only."""
    keywords = (
        "remember", "memory", "recall", "forget", "procedure", "playbook",
        "schedule", "remind", "every day", "every hour", "watch for",
        "event watcher", "trigger an event",
    )

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.keywords)


__all__ = ["UtilityAgent"]
