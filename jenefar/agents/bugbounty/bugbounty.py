from jenefar.core.agent import AgentContext, AgentResult, BaseAgent

class BugBountyAgent(BaseAgent):
    name="bugbounty"
    description="Authorized bug-bounty and application-security specialist"
    keywords=("bug bounty","bugbounty","burp","xss","sqli","idor","recon","intigriti","hackerone")

    def can_handle(self,text:str)->bool:
        t=text.lower()
        return any(k in t for k in self.keywords)

    def run(self,context:AgentContext)->AgentResult:
        return AgentResult(self.name, f"Bug-bounty specialist received: {context.task}")