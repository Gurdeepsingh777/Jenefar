from jenefar.core.agent import AgentContext, AgentResult, BaseAgent

class ResearchAgent(BaseAgent):
    name="research"
    description="General research and information synthesis specialist"

    def can_handle(self,text:str)->bool:
        return True

    def run(self,context:AgentContext)->AgentResult:
        return AgentResult(self.name, f"Research specialist received: {context.task}")