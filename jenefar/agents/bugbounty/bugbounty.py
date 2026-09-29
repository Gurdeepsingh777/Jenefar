from jenefar.agents.llm_agent import BaseLLMAgent

class BugBountyAgent(BaseLLMAgent):
    name = "bugbounty"
    description = "Authorized bug-bounty and application-security specialist"
    system_prompt = """You are Jenefar's authorized bug-bounty and application-security
specialist. Help with recon methodology, secure testing, triage, reproduction,
impact analysis and report writing for assets the user is authorized to test.
Do not turn requests into unrestricted targeting or destructive automation."""
    keywords = ("bug bounty","bugbounty","burp","xss","sqli","idor","recon","intigriti","hackerone")

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in self.keywords)
