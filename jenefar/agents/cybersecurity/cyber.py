from jenefar.core.agent import AgentContext, AgentResult, BaseAgent

class CybersecurityAgent(BaseAgent):
    name="cybersecurity"
    description="Cybersecurity and defensive security specialist"
    keywords=("cybersecurity","security","kali","linux","nmap","vulnerability","cve","malware","network")

    def can_handle(self,text:str)->bool:
        t=text.lower()
        return any(k in t for k in self.keywords)

    def run(self,context:AgentContext)->AgentResult:
        return AgentResult(self.name, f"Cybersecurity specialist received: {context.task}")