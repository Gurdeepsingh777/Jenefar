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
        graph_text = ""
        if graph:
            graph_text = "\nRelevant knowledge graph relations:\n" + "\n".join(
                f"{item.get('subject')} --{item.get('predicate')}--> {item.get('object')}"
                for item in graph[:8]
            )

        response = self.llm.complete(
            f"Task:\n{context.task}{history_text}{memory_text}{graph_text}",
            instructions=self.system_prompt,
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
    ) -> AgentResult:
        result_text = "\n\n".join(
            f"Tool: {item.get('tool', 'unknown')}\nResult: {item.get('result', '')}"
            for item in tool_results
        )
        response = self.llm.complete(
            (
                "Original user task:\n"
                f"{task}\n\n"
                "Approved local tool results are available below. "
                "Use them as execution evidence and provide the final answer. "
                "Do not claim any tool action that is not represented in these results.\n\n"
                f"{result_text}"
            ),
            instructions=self.system_prompt,
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
