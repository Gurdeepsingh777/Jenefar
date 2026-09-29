from jenefar.core.agent import AgentContext, AgentResult, BaseAgent

class PythonAgent(BaseAgent):
    name="python"
    description="Python programming and debugging specialist"
    keywords=("python","pip","pytest","django","fastapi","flask","script","code")

    def can_handle(self,text:str)->bool:
        t=text.lower()
        return any(k in t for k in self.keywords)

    def run(self,context:AgentContext)->AgentResult:
        return AgentResult(self.name, f"Python specialist received: {context.task}")