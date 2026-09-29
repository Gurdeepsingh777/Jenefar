from jenefar.agents.llm_agent import BaseLLMAgent

class RepositoryAgent(BaseLLMAgent):
    name = "repository"
    description = "GitHub repository analysis, architecture review and change-planning specialist"
    use_tools = True
    system_prompt = """You are Jenefar's repository engineering specialist.
Analyze public GitHub repositories without executing downloaded code. Use repository
analysis and change-planning tools when appropriate. Distinguish observed repository
facts from your proposed changes. Never claim a remote edit was performed unless a
separate write-capable tool explicitly confirms it."""
    keywords = (
        "github", "repository", "repo", "pull request", "pull-request",
        "patch", "refactor repository", "codebase", "architecture review",
        "repository analysis",
    )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in self.keywords)
