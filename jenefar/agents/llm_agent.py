from __future__ import annotations

import os

from jenefar.core.agent import AgentContext, AgentResult, BaseAgent
from jenefar.core.llm import LLMClient


class BaseLLMAgent(BaseAgent):
    system_prompt = "You are a helpful Jenefar specialist."
    use_web_search = False
    use_tools = False
    allow_action_tools = False
    model_env: str | None = None

    def __init__(self, tool_broker=None):
        configured_model = os.getenv(self.model_env, "").strip() if self.model_env else ""
        self.llm = LLMClient(model=configured_model or None)
        self.tool_broker = tool_broker

    @staticmethod
    def _language_instruction(response_language: str | None) -> str:
        if str(response_language or "").lower() != "hinglish":
            return ""
        return (
            "\nResponse language preference: Hinglish. "
            "Reply naturally in a Hindi-English mix using Roman Hindi, "
            "while keeping technical names, commands, code, filenames, APIs, "
            "and standard English terminology unchanged. "
            "Do not translate code or command syntax."
        )

    def run(self, context: AgentContext) -> AgentResult:
        history = context.metadata.get("history", [])
        history_text = ""
        if history:
            history_text = "\nRecent conversation:\n" + "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in history[-8:]
            )

        retrieved = context.metadata.get("retrieved_memory", [])
        memory_text = ""
        if retrieved:
            memory_text = "\nRelevant long-term memory:\n" + "\n".join(
                f"[{item.get('title', 'memory')}] {item.get('content', '')}"
                for item in retrieved[:6]
            )

        graph = context.metadata.get("knowledge_graph", [])
        runtime_text = context.metadata.get("runtime", {})
        capability_text = context.metadata.get("capabilities", [])
        graph_text = ""
        if graph:
            graph_text = "\nRelevant knowledge graph relations:\n" + "\n".join(
                f"{item.get('subject')} --{item.get('predicate')}--> {item.get('object')}"
                for item in graph[:8]
            )

        instructions = self.system_prompt + self._language_instruction(
            context.metadata.get("response_language")
        )
        if runtime_text:
            instructions += f"\nRuntime status: {runtime_text.get('connectivity', 'unknown')}. Offline limitations: {runtime_text.get('offline_limitations', [])}"
        if capability_text:
            instructions += "\nUser-requested capability scope:\n" + "\n".join(f"- {item.get('capability', '')}" for item in capability_text[-20:])
        response = self.llm.complete(
            f"Task:\n{context.task}{history_text}{memory_text}{graph_text}",
            instructions=instructions,
            use_web_search=self.use_web_search,
            tool_broker=self.tool_broker if self.use_tools else None,
            allow_action_tools=self.allow_action_tools,
        )
        return AgentResult(
            agent=self.name,
            content=response.text,
            metadata={
                "provider": response.provider,
                "response_id": response.response_id,
                "pending_tools": response.pending_tools,
            },
        )

    def continue_after_tools(
        self,
        task: str,
        tool_results: list[dict[str, object]],
        response_language: str | None = None,
    ) -> AgentResult:
        result_text = "\n\n".join(
            f"Tool: {item.get('tool', 'unknown')}\nResult: {item.get('result', '')}"
            for item in tool_results
        )
        instructions = self.system_prompt + self._language_instruction(response_language)
        response = self.llm.complete(
            (
                "Original user task:\n"
                f"{task}\n\n"
                "Approved local tool results are available below. "
                "Use them as execution evidence and provide the final answer. "
                "Do not claim any tool action that is not represented in these results.\n\n"
                f"{result_text}"
            ),
            instructions=instructions,
            use_web_search=self.use_web_search,
            tool_broker=None,
            allow_action_tools=False,
        )
        return AgentResult(
            agent=self.name,
            content=response.text,
            metadata={
                "provider": response.provider,
                "response_id": response.response_id,
            },
        )
