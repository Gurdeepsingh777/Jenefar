from __future__ import annotations

from jenefar.core.agent import AgentContext, AgentResult, BaseAgent
from jenefar.core.llm import LLMClient

class BaseLLMAgent(BaseAgent):
    system_prompt = "You are a helpful Jenefar specialist."
    use_web_search = False
    use_tools = False
    allow_action_tools = False

    def __init__(self, tool_broker=None):
        self.llm = LLMClient()
        self.tool_broker = tool_broker

    def run(self, context: AgentContext) -> AgentResult:
        history = context.metadata.get("history", [])
        history_text = ""
        if history:
            history_text = "\nRecent conversation:\n" + "\n".join(
                f"{m.get('role','user')}: {m.get('content','')}" for m in history[-8:]
            )

        response = self.llm.complete(
            f"Task:\n{context.task}{history_text}",
            instructions=self.system_prompt,
            use_web_search=self.use_web_search,
            tool_broker=self.tool_broker if self.use_tools else None,
            allow_action_tools=self.allow_action_tools,
        )
        return AgentResult(
            agent=self.name,
            content=response.text,
            metadata={"provider": response.provider, "response_id": response.response_id},
        )
