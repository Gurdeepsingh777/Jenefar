from __future__ import annotations

from jenefar.core.agent import AgentContext, AgentResult, BaseAgent
from jenefar.core.llm import LLMClient

class BaseLLMAgent(BaseAgent):
    system_prompt = "You are a helpful Jenefar specialist."
    use_web_search = False

    def __init__(self):
        self.llm = LLMClient()

    def run(self, context: AgentContext) -> AgentResult:
        history = context.metadata.get("history", [])
        history_text = ""
        if history:
            history_text = "\nRecent conversation:\n" + "\n".join(
                f"{m.get('role','user')}: {m.get('content','')}" for m in history[-8:]
            )
        prompt = f"Task:\n{context.task}{history_text}"
        response = self.llm.complete(
            prompt,
            instructions=self.system_prompt,
            use_web_search=self.use_web_search,
            safety_identifier=context.metadata.get("session_id"),
        )
        return AgentResult(
            agent=self.name,
            content=response.text,
            metadata={"provider": response.provider, "response_id": response.response_id},
        )
