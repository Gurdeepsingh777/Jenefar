from jenefar.agents.llm_agent import BaseLLMAgent

class PythonAgent(BaseLLMAgent):
    name = "python"
    description = "Python programming, debugging, testing and software engineering specialist"
    system_prompt = """You are Jenefar's Python/software-engineering specialist.
Give correct, practical answers. Explain code when useful. Prefer runnable Python and
safe debugging advice. Do not invent execution results."""
    keywords = ("python","pip","pytest","django","fastapi","flask","script","code")

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in self.keywords)
