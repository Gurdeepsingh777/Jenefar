from jenefar.agents.llm_agent import BaseLLMAgent

class ResearchAgent(BaseLLMAgent):
    name = "research"
    description = "Web research and information synthesis specialist"
    system_prompt = """You are Jenefar's research specialist.
Use web search when useful for current or source-sensitive questions. Clearly
separate verified facts from uncertainty and cite sources when the model provides them."""
    use_web_search = True
    use_tools = True

    def can_handle(self, text: str) -> bool:
        return True
